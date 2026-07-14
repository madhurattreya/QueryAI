import sys

print(sys.executable)
print(sys.version)
import re
import sys
import time
from ollama import chat
import pandas as pd
from sqlalchemy import inspect

# Import modular components
import backend.services.loader as loader
import backend.services.security as security
import backend.services.router as router
import backend.services.engine as engine_mod
import backend.services.formatter as formatter

# 1. Setup Data Source
datasets, engine, db_flavor = loader.setup_data_source()

# Inspect full schema description (used for suggestions and default logging)
schemas_desc = ""
table_names = []
if engine:
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        for table in table_names:
            columns = inspector.get_columns(table)
            col_desc = ", ".join([f"{col['name']} ({col['type']})" for col in columns])
            schemas_desc += f"Table: {table}\nColumns: {col_desc}\n\n"
        print(f"\n[INFO] Loaded tables from database: {table_names}")
    except Exception as ex:
        print(f"Error inspecting database tables: {ex}")
        exit(1)
else:
    for name, df_item in datasets.items():
        schemas_desc += f"\nDataset name: {name}\nColumns and Types:\n{df_item.dtypes.to_string()}\nFirst 3 sample rows:\n{df_item.head(3).to_string(index=False)}\n"
    print(f"\n[INFO] Loaded datasets: {list(datasets.keys())}")

# Load query cache
query_cache = engine_mod.load_cache()

print("\n[INFO] AI Data Analyst is Ready!")
if formatter.explain_mode:
    print("[MODE] Conversational mode active.")
elif formatter.debug_mode:
    print("[MODE] Debug mode active.")
elif formatter.fast_mode:
    print("[MODE] Fast/Result-only mode active.")
else:
    print("[MODE] Performance mode active. (Run with '--explain' to see natural language summaries).")
print("Type 'exit', 'quit' or 'bye' to stop.\n")

# -------------------------------
# Continuous Question Loop
# -------------------------------
while True:

    question = input("Ask a question: ")

    if question.lower() in ["exit", "quit", "bye"]:
        print("Goodbye!")
        break

    start_time = time.time()
    code = None
    q_key = question.strip().lower()

    try:
        # Step 2: Caching check
        if q_key in query_cache:
            code = query_cache[q_key]
            if formatter.debug_mode:
                print(f"[CACHE HIT] Loaded generated query from query_cache.json")
        else:
            # Step 3: Dataset pre-selection routing
            available_sources = list(datasets.keys()) if not engine else table_names
            relevant_sources = router.select_relevant_sources(question, available_sources)
            
            if formatter.debug_mode:
                print(f"[ROUTING] Selected relevant sources: {relevant_sources}")

            # Build schema description ONLY for selected sources
            selected_schema_desc = ""
            if engine:
                inspector = inspect(engine)
                for table in relevant_sources:
                    columns = inspector.get_columns(table)
                    col_desc = ", ".join([f"{col['name']} ({col['type']})" for col in columns])
                    selected_schema_desc += f"Table: {table}\nColumns: {col_desc}\n\n"
            else:
                for name in relevant_sources:
                    df_item = datasets[name]
                    selected_schema_desc += f"\nDataset name: {name}\nColumns and Types:\n{df_item.dtypes.to_string()}\nFirst 3 sample rows:\n{df_item.head(3).to_string(index=False)}\n"

            # Step 4: Prompt Construction & LLM Call 1
            if engine:
                prompt = f"""
You are an expert Data Analyst and an SQL Query generator.
You are given a relational database. Here is the schema for the relevant tables needed for this query:

{selected_schema_desc}

Rules:
1. Write a single SELECT SQL query that answers the user's question.
2. Output ONLY the SQL code block enclosed in ```sql ... ```. Do not include explanations, markdown comments outside the code block, or other text.
3. NEVER generate any queries other than SELECT queries. Do not use write operations like INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE.
4. Ensure the query runs on standard SQL (compatible with {db_flavor} databases).
5. NEVER use SELECT * - always list column names explicitly.

Question:
{question}
"""
            else:
                chart_rule = ""
                if engine_mod.HAS_PLOTLY:
                    chart_rule = "\n15. If the user asks for a chart or plot, you can use Plotly Express (available as pre-imported variable 'px') or Plotly Graph Objects (available as 'go') to create it. Always save the figure to 'chart.png' (static) using `fig.write_image('chart.png')` and to 'chart.html' (interactive HTML) using `fig.write_html('chart.html')`. Assign the string 'Chart saved to chart.png and chart.html' to the variable 'result'."
                else:
                    chart_rule = "\n15. If the user asks for a chart or plot, tell them that Plotly is not installed. Set result = 'Plotly is required for charts.'"

                prompt = f"""
You are an expert Data Analyst and a Python code generator for Pandas.
You have access to the following datasets (available as pre-loaded Pandas DataFrames):

{selected_schema_desc}

Rules:
1. Write a Python code snippet that answers the user's question.
2. The final result of your computation must be stored in a variable named 'result'.
3. Output ONLY the Python code block enclosed in ```python ... ```. Do not include explanations or other text.
4. Do not import pandas or load any files. Assume the DataFrames are already loaded and available in the global scope by their dataset names.
5. The variable 'result' can hold a single value (string, number, date) or a subset DataFrame/Series.
6. NEVER import anything.
7. NEVER define functions or classes.
8. NEVER use loops (while, for) or lambda expressions.
9. NEVER use try/except blocks.
10. NEVER access magic attributes beginning with "__".
11. NEVER access the filesystem or network.
12. NEVER use globals() or locals().
13. Only generate executable pandas expressions.{chart_rule}

Question:
{question}
"""

            response = chat(
                model="qwen2.5:7b",
                messages=[{"role": "user", "content": prompt}]
            )
            raw_content = response["message"]["content"].strip()

            # Parse query block
            if engine:
                code_match = re.search(r"```sql\s*(.*?)\s*```", raw_content, re.DOTALL | re.IGNORECASE)
                if code_match:
                    code = code_match.group(1).strip()
                else:
                    code_match2 = re.search(r"```\s*(.*?)\s*```", raw_content, re.DOTALL)
                    code = code_match2.group(1).strip() if code_match2 else raw_content.strip()
            else:
                code_match = re.search(r"```python\s*(.*?)\s*```", raw_content, re.DOTALL | re.IGNORECASE)
                if code_match:
                    code = code_match.group(1).strip()
                else:
                    code_match2 = re.search(r"```\s*(.*?)\s*```", raw_content, re.DOTALL)
                    code = code_match2.group(1).strip() if code_match2 else raw_content.strip()

                # Prep python wrapper
                lines = [line for line in code.split("\n") if line.strip()]
                if lines and not any(re.match(r"^\s*result\s*=", line) for line in lines):
                    last_line = lines[-1].strip()
                    print_match = re.match(r"^print\((.*)\)$", last_line)
                    if print_match:
                        lines[-1] = f"result = {print_match.group(1)}"
                    else:
                        lines[-1] = f"result = {last_line}"
                    code = "\n".join(lines)

            # Store to cache
            query_cache[q_key] = code
            engine_mod.save_cache(query_cache)

        # Step 5: Execution under sandbox rules
        if engine:
            # Validate SQL query
            security.validate_sql(code)
            
            # Run SQL query with timeout
            def run_sql():
                return pd.read_sql(code, engine)
                
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_sql)
                try:
                    result = future.result(timeout=5)
                except concurrent.futures.TimeoutError:
                    raise TimeoutError("SQL Query execution timed out after 5 seconds.")
        else:
            # Validate Pandas code safety
            security.validate_code(code)

            # Namespace prep
            safe_builtins = {
                'len': len, 'str': str, 'int': int, 'float': float, 'sum': sum,
                'max': max, 'min': min, 'abs': abs, 'any': any, 'all': all,
                'zip': zip, 'enumerate': enumerate, 'range': range, 'list': list,
                'dict': dict, 'set': set, 'tuple': tuple, 'bool': bool, 'round': round
            }
            local_vars = {name: df_item for name, df_item in datasets.items()}
            local_vars["result"] = None
            if engine_mod.HAS_PLOTLY:
                local_vars["go"] = engine_mod.go
                local_vars["px"] = engine_mod.px

            # Run with 5-second timeout
            engine_mod.run_query_with_timeout(code, {"__builtins__": safe_builtins}, local_vars, timeout=5)
            result = local_vars.get("result")
            
            if result is None:
                raise ValueError("The generated code did not assign any value to 'result'.")

        # Step 6: Conversational summary formatting if explanation mode is enabled
        explanation = None
        if formatter.explain_mode or formatter.debug_mode:
            summary_prompt = f"""
You are an expert Data Analyst.
Answer the user's question conversationally based on the calculated result from the dataset.

Question:
{question}

Calculated Result:
{result.to_string() if isinstance(result, (pd.DataFrame, pd.Series)) else result}

Rules:
1. Write a direct, friendly, and natural language response.
2. Do not mention coding syntax, SQL, variable names, or pandas in your response.
3. Keep it concise.
"""
            summary_response = chat(
                model="qwen2.5:7b",
                messages=[{"role": "user", "content": summary_prompt}]
            )
            explanation = summary_response["message"]["content"].strip()

        # Step 7: Output rendering
        time_taken = time.time() - start_time
        model_name = "Qwen2.5:7B"
        dataset_rows = len(result) if isinstance(result, (pd.DataFrame, pd.Series)) else 1

        # Log metrics to CSV
        engine_mod.log_query(question, code, time_taken, dataset_rows)

        # Print layout card
        formatter.print_structured_output(
            question=question,
            code=code,
            result=result,
            explanation=explanation,
            elapsed_time=time_taken,
            rows_count=dataset_rows,
            model_name=model_name,
            prompt=prompt if not q_key in query_cache else None
        )

        # Step 8: Show follow-up suggestions
        result_summary = str(result) if not isinstance(result, (pd.DataFrame, pd.Series)) else f"DataFrame with {len(result)} rows"
        formatter.show_followup_suggestions(question, schemas_desc, result_summary)

    except Exception as e:
        time_taken = time.time() - start_time
        # Log failure
        engine_mod.log_query(question, code if code else "FAILED GENERATION", time_taken, 0)
        formatter.print_error_output(question, str(e), time_taken, "Qwen2.5:7B", 0)