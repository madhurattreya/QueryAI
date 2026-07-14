import os
import re
import time
import json
import uuid
import hashlib
import pandas as pd
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import inspect
import concurrent.futures

import backend.config as config
from backend.models.schemas import QueryRequest
import backend.services.security as security
import backend.services.engine as engine
import backend.services.router as router_service
import backend.services.formatter as formatter
from backend.services.llm import LLMManager
import backend.services.history_db as db
import backend.services.schema_cache as schema_cache
import backend.services.prompt_builder as prompt_builder
import backend.services.logger as logger_service
from backend.models.context import ExecutionContext

router = APIRouter(prefix="/api")

try:
    import plotly.graph_objects as go
    def stub_write_image(self, *args, **kwargs):
        path = args[0] if args else kwargs.get("file") or kwargs.get("path")
        if isinstance(path, str):
            base = os.path.basename(path)
            uuid_str, _ = os.path.splitext(base)
            json_path = os.path.join(os.path.dirname(path), f"{uuid_str}.json")
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    f.write(self.to_json())
            except Exception:
                pass
        return None
    go.Figure.write_image = stub_write_image
except ImportError:
    pass

# Workspace root path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHARTS_DIR = os.path.join(WORKSPACE_ROOT, "data", "charts")
RESULTS_DIR = os.path.join(WORKSPACE_ROOT, "data", "results")

# Clean up charts on start
try:
    db.cleanup_charts(max_age_days=7, max_charts=1000)
except Exception:
    pass

def estimate_tokens(prompt: str) -> int:
    words = len(prompt.split())
    chars = len(prompt)
    return int(words * 1.2 + (chars - words * 5) * 0.25)

def get_active_dataset_details() -> tuple:
    """
    Returns (dataset_name, dataset_hash, dataset_id).
    """
    active_name = "unknown"
    active_hash = "no_data"
    
    if config.current_source_type == "file" and config.datasets:
        active_name = list(config.datasets.keys())[0]  # default fallback name
        active_hash = "|".join([f"{k}:{engine.get_df_hash(v)}" for k, v in sorted(config.datasets.items())])
    elif config.current_source_type == "sql" and config.database_engine:
        active_name = config.db_flavor or "sql"
        active_hash = str(config.database_engine.url)
        
    ds_id = db.get_or_create_dataset(active_name)
    return active_name, active_hash, ds_id

def background_tasks_worker(
    conv_id: str,
    user_msg_id: str,
    assistant_msg_id: str,
    question: str,
    code: str,
    result_preview_str: str,
    result_file_path: str,
    chart_id: str,
    explanation: str,
    time_taken: float,
    dataset_rows: int,
    prompt_size: int,
    engine_used: str,
    debug_info_str: str,
    chart_png_path: str,
    chart_html_path: str,
    chart_meta_path: str,
    dataset_id: str
):
    """
    Worker function to process log writes, chart database indexes, summaries and cleanup in background threads.
    """
    # 1. Save user message to database
    db.add_message(
        conv_id=conv_id,
        role="user",
        content=question
    )

    # 2. Save assistant response to database
    db.add_message(
        conv_id=conv_id,
        role="assistant",
        content=explanation or "Result processed.",
        generated_code=code,
        result_preview=result_preview_str,
        result_file=result_file_path,
        chart_id=chart_id,
        execution_time=time_taken,
        rows=dataset_rows,
        prompt_size=prompt_size,
        engine_used=engine_used,
        debug_info=debug_info_str
    )

    # 3. Add chart indexing to DB if requested and exists
    if chart_id and os.path.exists(chart_html_path):
        os.makedirs(CHARTS_DIR, exist_ok=True)
        with open(chart_meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "id": chart_id,
                "conversation_id": conv_id,
                "question": question,
                "created_at": datetime.now().isoformat(),
                "dataset_id": dataset_id,
                "rows": dataset_rows
            }, f)
        db.add_chart(chart_id, conv_id, assistant_msg_id, dataset_id, question, "plotly", chart_html_path, chart_png_path)

    # 4. Trigger Conversation Summary after 10 total turns
    all_messages = db.get_messages(conv_id, limit=None)
    if len(all_messages) >= 10 and len(all_messages) % 5 == 0:
        history_text = ""
        for m in all_messages:
            history_text += f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:100]}\n"
        
        summary_prompt = prompt_builder.build_prompt("summary", history_text=history_text)
        try:
            model = config.settings.get("model", "qwen2.5:7b")
            manager = LLMManager()
            summary, _ = manager.call_llm_with_fallback(summary_prompt, model)
            db.update_conversation_summary(conv_id, summary.strip())
        except Exception:
            pass

    # 5. Telemetry log appending
    try:
        debug_info = json.loads(debug_info_str) if debug_info_str else {}
        logger_service.log_telemetry({
            "status": "success",
            "conversation_id": conv_id,
            "engine_used": engine_used,
            "execution_time": time_taken,
            "rows_returned": dataset_rows,
            "prompt_size": prompt_size,
            "model_used": debug_info.get("model", "unknown"),
            "timings": debug_info.get("timings", {})
        })
    except Exception:
        pass

    # 6. Cleanup old charts
    try:
        db.cleanup_charts(max_age_days=7, max_charts=1000)
    except Exception:
        pass
        
    # 7. Persist cache to disk
    try:
        engine.persist_cache_to_disk()
    except Exception:
        pass


def execute_query_stream(req: QueryRequest, background_tasks: BackgroundTasks):
    """
    S synchronous stream generator executing queries with SSE progress states.
    """
    total_start = time.time()
    
    # Time measurements dict
    timings = {
        "Routing": 0.0,
        "Cache lookup": 0.0,
        "Schema lookup": 0.0,
        "Dataset loading": 0.0,
        "Prompt creation": 0.0,
        "Planner": 0.0,
        "Generator": 0.0,
        "Execution": 0.0,
        "Chart generation": 0.0,
        "Formatting": 0.0,
        "Serialization": 0.0,
        "Response": 0.0
    }
    
    yield json.dumps({"type": "progress", "step": "Receiving Request"}) + "\n"
    question = req.question
    conversation_id = req.conversation_id
    assistant_msg_id = str(uuid.uuid4())
    
    # Load Conversation details
    t_start = time.time()
    if not conversation_id or not db.get_conversation(conversation_id):
        conversation_id = db.create_conversation(title=question[:50])
    
    conv_details = db.get_conversation(conversation_id)
    timings["Routing"] += time.time() - t_start

    # Get active source metadata
    yield json.dumps({"type": "progress", "step": "Loading Active Dataset"}) + "\n"
    t_start_ds = time.time()
    dataset_name, dataset_hash, dataset_id = get_active_dataset_details()
    timings["Dataset loading"] = time.time() - t_start_ds
    
    # Guard: No active dataset loaded or SQL connection broken
    no_file_data = config.current_source_type == "file" and not config.datasets
    no_sql_engine = config.current_source_type == "sql" and not config.database_engine
    if no_file_data or no_sql_engine:
        source_label = "database" if config.current_source_type == "sql" else "file dataset"
        yield json.dumps({
            "type": "error",
            "status": "error",
            "error": (
                f"No active {source_label} is currently loaded. "
                "Please go to the Datasets tab and set an active dataset before running a query. "
                "If you connected a database, make sure the connection is valid and click 'Set Active'."
            ),
            "time_taken": round(time.time() - total_start, 3)
        }) + "\n"
        return

    # Guard: Test SQL connection is actually live (SQLAlchemy is lazy — engine existing != connection working)
    if config.current_source_type == "sql" and config.database_engine:
        try:
            from sqlalchemy import text
            with config.database_engine.connect() as test_conn:
                test_conn.execute(text("SELECT 1"))
        except Exception as conn_err:
            yield json.dumps({
                "type": "error",
                "status": "error",
                "error": (
                    f"Cannot connect to the database: {str(conn_err)[:200]}. "
                    "Please check that your database server is running and accessible, "
                    "then reconnect from the Datasets tab."
                ),
                "time_taken": round(time.time() - total_start, 3)
            }) + "\n"
            return

    # Auto-Reset Context on Dataset switch
    if conv_details and conv_details.get("dataset_id") != dataset_id:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        cursor.execute("UPDATE conversations SET dataset_id = ?, summary = NULL WHERE id = ?", (dataset_id, conversation_id))
        conn.commit()
        conn.close()
        conv_details["summary"] = None

    # Step 1: Query Engine & Complexity Classification
    yield json.dumps({"type": "progress", "step": "Routing Query"}) + "\n"
    
    t_start_route = time.time()
    router_res = router_service.classify_query_engine_detailed(question)
    engine_type = router_res["engine"]
    complexity = router_service.detect_complexity(question)
    fallback_reason = router_res.get("fallback_reason")
    llm_used = router_res.get("llm_used", False)
    parsed_query = router_res.pop("parsed_query", None)
    timings["Routing"] += time.time() - t_start_route
    
    # Step 2: Schema extraction
    yield json.dumps({"type": "progress", "step": "Building Cached Schema"}) + "\n"
    
    t_start_schema = time.time()
    available_sources = list(config.datasets.keys()) if config.current_source_type == "file" else []
    if config.current_source_type == "sql" and config.database_engine:
        try:
            inspector = inspect(config.database_engine)
            available_sources = inspector.get_table_names()
        except Exception:
            pass
            
    relevant_sources = router_service.select_relevant_sources(question, available_sources)
    
    # Retrieve Cached schemas & profiles
    selected_schema_desc = ""
    selected_profile_desc = ""
    for name in relevant_sources:
        selected_schema_desc += schema_cache.get_table_schema(name) + "\n"
        selected_profile_desc += schema_cache.get_table_profile(name) + "\n"
        
    timings["Schema lookup"] = time.time() - t_start_schema

    # Step 3: SHA256 Result Caching check
    t_start_cache = time.time()
    model = config.settings.get("model", "qwen2.5:7b")
    temperature = 0.0
    
    # Calculate template and context hashes
    from backend.services.prompt_builder import get_template
    template_text = get_template(engine_type or "pandas")
    prompt_template_hash = hashlib.sha256(template_text.encode("utf-8")).hexdigest()
    
    summary = conv_details.get("summary") if conv_details else ""
    conversation_context_hash = hashlib.sha256((summary or "").encode("utf-8")).hexdigest()
    
    cache_key = engine.get_sha256_cache_key(
        dataset_hash=dataset_hash,
        question=question,
        conversation_id=conversation_id,
        selected_model=model,
        temperature=temperature,
        dataset_version=dataset_id,
        router_type=engine_type,
        prompt_template_hash=prompt_template_hash,
        conversation_context_hash=conversation_context_hash
    )
    
    cached_val = engine.get_cached_result(cache_key)
    timings["Cache lookup"] = time.time() - t_start_cache
    
    if cached_val:
        yield json.dumps({"type": "progress", "step": "Cache hit! Returning cached result..."}) + "\n"
        
        # Prepare response dict
        timings["Serialization"] = 0.001
        timings["Response"] = time.time() - total_start
        
        # Determine slowest stage dynamically
        max_val = -1.0
        slowest = "None"
        for stage, val in timings.items():
            if stage != "Response" and val > max_val:
                max_val = val
                slowest = stage
        
        cached_val["cached"] = True
        cached_val["conversation_id"] = conversation_id
        cached_val["execution_time"] = round(timings["Response"], 3)
        cached_val["type"] = "success"
        
        cached_val["debug_info"]["timings"] = {k: round(v, 4) for k, v in timings.items()}
        cached_val["debug_info"]["cache_hit"] = True
        cached_val["debug_info"]["slowest_stage"] = f"{slowest} ({max_val * 1000:.1f}ms)"
        yield json.dumps(cached_val) + "\n"
        return

    # Setup context variables
    context = ExecutionContext(
        conversation_id=conversation_id,
        dataset_id=dataset_id,
        dataset_version=dataset_id,
        engine=engine_type,
        schema_desc=selected_schema_desc,
        profile_desc=selected_profile_desc,
        model=model,
        question=question,
        complexity=complexity,
        chart_requested=engine_type == "visualization"
    )

    # Step 4: Execution Plan Generation (Conditional Planning)
    plan_block = ""
    if complexity == "complex" and engine_type in ["aggregation", "filter", "visualization", "prediction"]:
        yield json.dumps({"type": "progress", "step": "Generating query execution plan..."}) + "\n"
        t_start = time.time()
        plan_prompt = prompt_builder.build_prompt(
            "planner",
            schema_desc=selected_schema_desc,
            profile_desc=selected_profile_desc,
            question=question
        )
        try:
            manager = LLMManager()
            plan, _ = manager.call_llm_with_fallback(plan_prompt, model, temperature)
            context.execution_plan = plan.strip()
            plan_block = f"Planned Steps:\n{context.execution_plan}\n"
        except Exception as e:
            print(f"[QUERY PLANNER WARNING] Planner failed: {str(e)}")
        timings["Planner"] = (time.time() - t_start)

    # Prepare chat history context (last 5 messages)
    recent_messages = db.get_messages(conversation_id, limit=5)
    history_block = ""
    if recent_messages:
        history_block = "\nRecent Conversation History:\n"
        for m in recent_messages:
            role_label = "User" if m["role"] == "user" else "Assistant"
            content_clean = m["content"]
            # Strip code blocks
            content_clean = re.sub(r"```.*?```", "[Code]", content_clean, flags=re.DOTALL)
            content_clean = content_clean[:120].strip()
            history_block += f"{role_label}: {content_clean}\n"
            
    summary_block = f"Conversation Summary: {conv_details.get('summary')}\n" if conv_details and conv_details.get("summary") else ""
    
    # Generate Chart paths in case chart requested
    chart_uuid = str(uuid.uuid4())
    chart_html_path = os.path.join(CHARTS_DIR, f"{chart_uuid}.html")
    chart_png_path = os.path.join(CHARTS_DIR, f"{chart_uuid}.png")
    chart_meta_path = os.path.join(CHARTS_DIR, f"{chart_uuid}_metadata.json")
    os.makedirs(CHARTS_DIR, exist_ok=True)

    result = None
    dataset_rows = 0
    active_chart_id = None
    
    # Check if we can execute deterministically without LLM
    if not llm_used:
        yield json.dumps({"type": "progress", "step": "Executing Plan (Deterministic Engine)"}) + "\n"
        
        # 1. Visualization Engine
        if engine_type == "visualization":
            t_start_chart = time.time()
            chart_type = parsed_query.chart_type
            
            # Recommendation logic:
            # Time series -> line, category comparison -> bar, single numeric -> histogram, others -> scatter
            known_cols = []
            active_df_name = ""
            active_df = None
            if config.datasets:
                active_df_name = list(config.datasets.keys())[0]
                active_df = config.datasets[active_df_name]
                known_cols = active_df.columns.tolist()
                
            if not chart_type and parsed_query.entities.get("matched_columns"):
                cols = parsed_query.entities["matched_columns"]
                if len(cols) >= 2:
                    col_x, col_y = cols[0], cols[1]
                    if "date" in col_x.lower() or "joined" in col_x.lower() or "hired" in col_x.lower():
                        chart_type = "line"
                    elif active_df is not None and active_df[col_x].dtype == 'object':
                        chart_type = "bar"
                    else:
                        chart_type = "scatter"
                else:
                    chart_type = "histogram"

            # If no file-based dataframe is available, fall through to LLM visualization path
            if active_df is None:
                yield json.dumps({"type": "error", "status": "error",
                    "error": "Chart generation requires a file-based dataset (CSV/Excel). SQL-based visualizations are handled via the LLM path.",
                    "time_taken": round(time.time() - total_start, 3)}) + "\n"
                return
                    
            cols = parsed_query.entities.get("matched_columns", [])
            col_x = cols[0] if len(cols) > 0 else (known_cols[0] if known_cols else None)
            col_y = cols[1] if len(cols) > 1 else None
            
            import backend.services.chart_factory as cf
            title = f"{chart_type.title() if chart_type else 'Scatter'} of {col_x}" + (f" vs {col_y}" if col_y else "")
            
            # Generate precompiled chart
            if chart_type == "bar":
                fig = cf.build_bar_chart(active_df, col_x, col_y, title)
            elif chart_type == "line":
                fig = cf.build_line_chart(active_df, col_x, col_y, title)
            elif chart_type == "box":
                fig = cf.build_box_plot(active_df, col_x, col_y, title)
            elif chart_type == "histogram":
                fig = cf.build_histogram(active_df, col_x, title)
            elif chart_type == "pie":
                fig = cf.build_pie_chart(active_df, col_x, col_y, title)
            elif chart_type == "heatmap":
                fig = cf.build_heatmap(active_df, title=title)
            elif chart_type == "area":
                fig = cf.build_area_chart(active_df, col_x, col_y, title)
            elif chart_type == "treemap":
                fig = cf.build_treemap(active_df, [col_x], col_y, title)
            else:
                fig = cf.build_scatter_chart(active_df, col_x, col_y or col_x, title)
                
            cf.create_chart_assets(fig, CHARTS_DIR, chart_uuid)
            
            result = "Chart saved to chart.png and chart.html"
            code = f"fig = px.{chart_type or 'scatter'}(df, x='{col_x}'" + (f", y='{col_y}'" if col_y else "") + f", title='{title}')\ncf.create_chart_assets(fig, CHARTS_DIR, '{chart_uuid}')"
            context.code = code
            context.raw_result = pd.DataFrame([{"Result": result}])
            context.explanation = f"Generated a predefined {chart_type or 'scatter'} chart for {col_x}" + (f" vs {col_y}." if col_y else ".")
            active_chart_id = chart_uuid
            timings["Chart generation"] = time.time() - t_start_chart
            
        # 2. Insights Engine
        elif engine_type == "insight":
            t_start_insight = time.time()
            from backend.services.insight_engine import generate_dataset_insights
            df_name = ""
            df = None
            if config.datasets:
                df_name = list(config.datasets.keys())[0]
                df = config.datasets[df_name]
            insights_text = generate_dataset_insights(df_name, df)
            context.explanation = insights_text
            context.raw_result = pd.DataFrame([{"Insights": insights_text}])
            code = "# Programmatic Insight Engine (no code executed)"
            context.code = code
            timings["Execution"] = time.time() - t_start_insight
            
        # 3. Lookup, Filter, Aggregation, Sorting, Ranking Engine
        else:
            t_start_exec = time.time()
            from backend.services.query_engine import execute_parsed_query
            
            df_name = ""
            df = None
            if config.datasets:
                df_name = list(config.datasets.keys())[0]
                df = config.datasets[df_name]
                
            result, code_expr = execute_parsed_query(parsed_query, df, df_name=df_name)
            context.raw_result = result
            code = f"result = {code_expr}"
            context.code = code
            
            if isinstance(result, (pd.DataFrame, pd.Series)):
                context.explanation = f"Found {len(result)} records matching your query."
            else:
                context.explanation = f"Calculated result: {result}"
                
            timings["Execution"] = time.time() - t_start_exec

            # Detailed Pipeline Audit Logging (stdout & system logger)
            rows_before = len(df) if df is not None else 0
            rows_after = len(result) if isinstance(result, (pd.DataFrame, pd.Series)) else (1 if result is not None else 0)
            
            audit_log = (
                f"\n============ DETERMINISTIC EXECUTION PIPELINE AUDIT ============\n"
                f"Question:             {question}\n"
                f"Parsed Intent:        {parsed_query.intent} (Confidence: {parsed_query.confidence})\n"
                f"Execution Plan:       {parsed_query.execution_plan}\n"
                f"Matched Dataset:      {df_name}\n"
                f"Matched Columns:      {parsed_query.entities.get('matched_columns', [])}\n"
                f"Applied Pandas Code:  {code}\n"
                f"Rows Before:          {rows_before}\n"
                f"Rows After:           {rows_after}\n"
                f"Execution Time:       {timings['Execution']:.6f}s\n"
                f"Returned Result:      {str(result)[:250]}...\n"
                f"================================================================\n"
            )
            print(audit_log)
            
        # Jump directly to serialization and response
        t_start_fmt = time.time()
        result = context.raw_result
        if isinstance(result, pd.DataFrame):
            dataset_rows = len(result)
            if dataset_rows > 100:
                os.makedirs(RESULTS_DIR, exist_ok=True)
                parquet_filename = f"{str(uuid.uuid4())}.parquet"
                result_file_path = os.path.join(RESULTS_DIR, parquet_filename)
                result.to_parquet(result_file_path)
                result_preview_str = json.dumps(result.head(100).to_dict(orient="records"))
            else:
                result_preview_str = json.dumps(result.to_dict(orient="records"))
                result_file_path = ""
        elif isinstance(result, pd.Series):
            series_dict = [{"Index": str(k), "Value": str(v)} for k, v in result.items()]
            result_preview_str = json.dumps(series_dict)
            result_file_path = ""
        else:
            result_preview_str = json.dumps([{"Result": str(result)}])
            result_file_path = ""
        timings["Formatting"] = time.time() - t_start_fmt
        
        t_start_ser = time.time()
        total_taken = time.time() - total_start
        timings["Response"] = total_taken
        
        # Calculate slowest stage dynamically
        max_val = -1.0
        slowest = "None"
        for stage, val in timings.items():
            if stage != "Response" and val > max_val:
                max_val = val
                slowest = stage
                
        debug_info = {
            "timings": {k: round(v, 4) for k, v in timings.items()},
            "complexity": complexity,
            "engine_used": engine_type,
            "prompt_size": 0,
            "model": "deterministic_query_engine",
            "cache_hit": False,
            "auto_retry_count": 0,
            "router_decision": router_res,
            "slowest_stage": f"{slowest} ({max_val * 1000:.1f}ms)",
            "cache_used": False,
            "llm_used": False,
            "parser_used": True,
            "question": question,
            "parsed_intent": parsed_query.intent,
            "execution_plan": parsed_query.execution_plan,
            "matched_dataset": df_name,
            "matched_columns": parsed_query.entities.get("matched_columns", []),
            "applied_pandas_code": code,
            "rows_before": len(df) if df is not None else 0,
            "rows_after": dataset_rows,
            "execution_time": timings.get("Execution", 0.0),
            "returned_result": result_preview_str
        }
        debug_info_str = json.dumps(debug_info)
        timings["Serialization"] = time.time() - t_start_ser
        
        # Save cache
        cached_payload = {
            "status": "success",
            "dataset_id": dataset_id,
            "model": "deterministic_query_engine",
            "rows": dataset_rows,
            "chart_id": active_chart_id,
            "result": json.loads(result_preview_str),
            "code": code,
            "explanation": context.explanation,
            "prompt_size": 0,
            "engine_used": engine_type,
            "debug_info": debug_info
        }
        engine.set_cached_result(cache_key, cached_payload)
        
        # Queue background task
        background_tasks.add_task(
            background_tasks_worker,
            conv_id=conversation_id,
            user_msg_id=str(uuid.uuid4()),
            assistant_msg_id=assistant_msg_id,
            question=question,
            code=code,
            result_preview_str=result_preview_str,
            result_file_path=result_file_path,
            chart_id=active_chart_id,
            explanation=context.explanation,
            time_taken=total_taken,
            dataset_rows=dataset_rows,
            prompt_size=0,
            engine_used=engine_type,
            debug_info_str=debug_info_str,
            chart_png_path=chart_png_path,
            chart_html_path=chart_html_path,
            chart_meta_path=chart_meta_path,
            dataset_id=dataset_id
        )
        
        final_payload = {
            "type": "success",
            "status": "success",
            "conversation_id": conversation_id,
            "dataset_id": dataset_id,
            "model": "deterministic_query_engine",
            "execution_time": round(total_taken, 3),
            "rows": dataset_rows,
            "chart_id": active_chart_id,
            "result": json.loads(result_preview_str),
            "code": code,
            "explanation": context.explanation,
            "prompt_size": 0,
            "engine_used": engine_type,
            "debug_info": debug_info
        }
        yield json.dumps(final_payload) + "\n"
        return

    # Step 5: Code Generation
    yield json.dumps({"type": "progress", "step": "Generating SQL/Pandas Code"}) + "\n"
    
    t_start_prompt = time.time()
    t_start_gen = time.time()
    code = None
    prompt = ""
    
    # Prompt selections
    if engine_type == "metadata":
        # Direct LLM lookup, no execution
        prompt = prompt_builder.build_prompt(
            "insight",
            schema_desc=selected_schema_desc,
            profile_desc=selected_profile_desc,
            summary_block=summary_block,
            history_block=history_block,
            question=question
        )
    elif engine_type == "general_chat":
        prompt = f"System: {prompt_builder.get_template('system')}\nUser: {question}"
    elif engine_type == "insight":
        prompt = "# Programmatic Insight Engine (no prompt needed)"
    elif engine_type == "visualization":
        prompt = prompt_builder.build_prompt(
            "chart",
            schema_desc=selected_schema_desc,
            profile_desc=selected_profile_desc,
            summary_block=summary_block,
            history_block=history_block,
            chart_png_path=chart_png_path.replace(os.sep, '/'),
            chart_html_path=chart_html_path.replace(os.sep, '/'),
            question=question
        )
    elif config.current_source_type == "sql" and config.database_engine:
        prompt = prompt_builder.build_prompt(
            "sql",
            schema_desc=selected_schema_desc,
            profile_desc=selected_profile_desc,
            summary_block=summary_block,
            history_block=history_block,
            plan_block=plan_block,
            db_flavor=config.db_flavor or "SQLite",
            question=question
        )
    else:
        prompt = prompt_builder.build_prompt(
            "pandas",
            schema_desc=selected_schema_desc,
            profile_desc=selected_profile_desc,
            summary_block=summary_block,
            history_block=history_block,
            plan_block=plan_block,
            question=question
        )
        
    context.prompt_size = estimate_tokens(prompt)
    context.prompt = prompt
    timings["Prompt creation"] = time.time() - t_start_prompt
    
    manager = LLMManager()
    t_start_gen = time.time()
    
    if engine_type not in ["metadata", "general_chat", "insight"]:
        # Execute LLM to generate code
        try:
            raw_content, final_model = manager.call_llm_with_fallback(prompt, model, temperature)
            context.model = final_model
            
            # Parse code block
            block_type = "sql" if (config.current_source_type == "sql" and config.database_engine and engine_type != "visualization") else "python"
            code_match = re.search(fr"```{block_type}\s*(.*?)\s*```", raw_content, re.DOTALL | re.IGNORECASE)
            if code_match:
                code = code_match.group(1).strip()
            else:
                code_match2 = re.search(r"```\s*(.*?)\s*```", raw_content, re.DOTALL)
                code = code_match2.group(1).strip() if code_match2 else raw_content.strip()
                
            # Post-wrap pandas expressions
            if block_type == "python":
                # Strip import statements dynamically
                code_lines = []
                for line in code.split("\n"):
                    trimmed = line.strip()
                    if not trimmed.startswith("import ") and not trimmed.startswith("from "):
                        code_lines.append(line)
                code = "\n".join(code_lines)
                
                # Strip browser-blocking fig.show() or show() calls
                code = re.sub(r'\bfig\.show\([^)]*\)', '', code)
                code = re.sub(r'\bshow\([^)]*\)', '', code)
                
                lines = [l for l in code.split("\n") if l.strip()]
                if lines and not any(re.match(r"^\s*result\s*=", l) for l in lines):
                    last_line = lines[-1].strip()
                    print_match = re.match(r"^print\((.*)\)$", last_line)
                    if print_match:
                        lines[-1] = f"result = {print_match.group(1)}"
                    else:
                        lines[-1] = f"result = {last_line}"
                    code = "\n".join(lines)
            context.code = code
        except Exception as e:
            context.error = f"Failed to generate query code: {str(e)}"
            yield json.dumps({"type": "error", "status": "error", "error": context.error, "time_taken": round(time.time() - total_start, 3)}) + "\n"
            return
    elif engine_type == "insight":
        try:
            from backend.services.insight_engine import generate_dataset_insights
            df_name = ""
            df = None
            if config.datasets:
                df_name = list(config.datasets.keys())[0]
                df = config.datasets[df_name]
            insights_text = generate_dataset_insights(df_name, df)
            context.explanation = insights_text
            context.raw_result = pd.DataFrame([{"Insights": insights_text}])
            code = "# Programmatic Insight Engine (no code executed)"
            context.code = code
        except Exception as e:
            context.error = f"Failed in Insight Engine: {str(e)}"
            yield json.dumps({"type": "error", "status": "error", "error": context.error, "time_taken": round(time.time() - total_start, 3)}) + "\n"
            return
    else:
        # Simple metadata / chat questions are answered directly
        try:
            raw_content, final_model = manager.call_llm_with_fallback(prompt, model, temperature)
            context.model = final_model
            context.explanation = raw_content.strip()
            context.raw_result = pd.DataFrame([{"Result": context.explanation}])
            code = "# Direct LLM response (no code executed)"
            context.code = code
        except Exception as e:
            context.error = f"Failed to generate LLM response: {str(e)}"
            yield json.dumps({"type": "error", "status": "error", "error": context.error, "time_taken": round(time.time() - total_start, 3)}) + "\n"
            return
            
    timings["Generator"] = time.time() - t_start_gen

    # Step 6: Code Sandbox Execution (with Self-Healing retry loop)
    result = None
    dataset_rows = 0
    auto_retry_count = 0
    
    if engine_type not in ["metadata", "general_chat", "insight"]:
        yield json.dumps({"type": "progress", "step": "Executing Sandbox"}) + "\n"
        
        t_start = time.time()
        
        # Compile all available column names for fuzzy mapping
        all_columns = []
        if config.current_source_type == "file":
            for df_item in config.datasets.values():
                all_columns.extend(df_item.columns.tolist())
        elif config.current_source_type == "sql" and config.database_engine:
            try:
                inspector = inspect(config.database_engine)
                for t in available_sources:
                    # Strip BOM from column names (common in MySQL imports from BOM-encoded CSVs)
                    all_columns.extend([col['name'].lstrip('\ufeff') for col in inspector.get_columns(t)])
            except Exception:
                pass
                
        # Sandbox runner wrapper
        def run_sandbox():
            nonlocal result
            if config.current_source_type == "sql" and config.database_engine and engine_type != "visualization":
                # Parameterize / SQL security limits
                security.validate_sql(code)
                # Max execution Cap 5s
                def run_sql():
                    return pd.read_sql(code, config.database_engine)
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as sql_executor:
                    sql_future = sql_executor.submit(run_sql)
                    result = sql_future.result(timeout=5)
            else:
                security.validate_code(code)
                safe_builtins = {
                    'len': len, 'str': str, 'int': int, 'float': float, 'sum': sum,
                    'max': max, 'min': min, 'abs': abs, 'any': any, 'all': all,
                    'zip': zip, 'enumerate': enumerate, 'range': range, 'list': list,
                    'dict': dict, 'set': set, 'tuple': tuple, 'bool': bool, 'round': round
                }
                local_vars = {name: df_item for name, df_item in config.datasets.items()}
                if config.datasets:
                    active_name = list(config.datasets.keys())[0]
                    local_vars["df"] = config.datasets[active_name]
                local_vars["result"] = None
                local_vars["pd"] = pd
                if engine.HAS_PLOTLY:
                    local_vars["go"] = engine.go
                    local_vars["px"] = engine.px
                    
                engine.run_query_with_timeout(code, {"__builtins__": safe_builtins}, local_vars, timeout=25)
                result = local_vars.get("result")
                if result is None:
                    raise ValueError("The generated code did not assign any value to 'result'.")

        # First run attempt
        try:
            run_sandbox()
        except Exception as primary_err:
            print(f"[SANDBOX EXECUTION FAILED] Error: {str(primary_err)}\nCode executed:\n{code}")
            # Self-healing attempt 1: Fuzzy correction
            auto_retry_count = 1
            yield json.dumps({"type": "progress", "step": "Query error: Attempting automatic fuzzy column correction..."}) + "\n"
            corrected = engine.attempt_fast_correction(code, primary_err, all_columns)
            
            if corrected:
                try:
                    code = corrected
                    context.code = code
                    run_sandbox()
                except Exception as fuzzy_err:
                    print(f"[FUZZY CORRECTION FAILED] Error: {str(fuzzy_err)}")
                    corrected = None
                    
            # Self-healing attempt 2: LLM-based correction retry
            if not corrected:
                yield json.dumps({"type": "progress", "step": "Fuzzy correction failed. Attempting LLM self-healing regeneration..."}) + "\n"
                t_llm_start = time.time()
                retry_prompt = prompt_builder.build_prompt(
                    "correction",
                    error_msg=str(primary_err),
                    failed_code=code,
                    schema_desc=selected_schema_desc,
                    profile_desc=selected_profile_desc
                )
                try:
                    raw_content, final_model = manager.call_llm_with_fallback(retry_prompt, model, temperature)
                    context.model = final_model
                    
                    block_type = "sql" if (config.current_source_type == "sql" and config.database_engine and engine_type != "visualization") else "python"
                    code_match = re.search(fr"```{block_type}\s*(.*?)\s*```", raw_content, re.DOTALL | re.IGNORECASE)
                    if code_match:
                        code = code_match.group(1).strip()
                    else:
                        code_match2 = re.search(r"```\s*(.*?)\s*```", raw_content, re.DOTALL)
                        code = code_match2.group(1).strip() if code_match2 else raw_content.strip()
                    
                    if block_type == "python":
                        code_lines = []
                        for line in code.split("\n"):
                            trimmed = line.strip()
                            if not trimmed.startswith("import ") and not trimmed.startswith("from "):
                                code_lines.append(line)
                        code = "\n".join(code_lines)
                        
                        # Strip browser-blocking fig.show() or show() calls
                        code = re.sub(r'\bfig\.show\([^)]*\)', '', code)
                        code = re.sub(r'\bshow\([^)]*\)', '', code)
                        
                    context.code = code
                    run_sandbox()
                except Exception as final_err:
                    context.error = f"Column reference error: {str(primary_err)}. Retry correction failed: {str(final_err)}"
                    yield json.dumps({"type": "error", "status": "error", "error": "The generated query referenced a column that does not exist. Attempting automatic regeneration.", "time_taken": round(time.time() - total_start, 3)}) + "\n"
                    # Log failure to telemetry
                    logger_service.log_telemetry({
                        "status": "error",
                        "conversation_id": conversation_id,
                        "engine_used": engine_type,
                        "execution_time": time.time() - total_start,
                        "error": context.error
                    })
                    return
                timings["Generator"] += (time.time() - t_llm_start)

        timings["Execution"] = time.time() - t_start
        context.raw_result = result
    else:
        result = context.raw_result

    # Format result rows count
    dataset_rows = len(result) if isinstance(result, (pd.DataFrame, pd.Series)) else 1
    context.rows = dataset_rows
    
    yield json.dumps({"type": "progress", "step": "Formatting Results"}) + "\n"
    
    # Step 7: Conditional Explanation Generation
    explanation = context.explanation
    wants_explain = config.settings.get("explain_mode", False) is True or any(w in question.lower() for w in ["explain", "summary", "insight", "interpretation", "why"])
    
    if wants_explain and not explanation:
        yield json.dumps({"type": "progress", "step": "Generating Explanation"}) + "\n"
        t_start = time.time()
        
        result_preview = result.to_string() if isinstance(result, (pd.DataFrame, pd.Series)) else str(result)
        # Cap result preview in prompt context to avoid tokens overflow
        if len(result_preview) > 1500:
            result_preview = result_preview[:1500] + "\n[INFO] Truncated for token optimization..."
            
        summary_prompt = prompt_builder.build_prompt(
            "explanation",
            question=question,
            result_str=result_preview
        )
        try:
            explanation, _ = manager.call_llm_with_fallback(summary_prompt, model, temperature)
            context.explanation = explanation.strip()
        except Exception as e:
            context.explanation = "Data processed successfully."
        timings["Generator"] += (time.time() - t_start)
    elif not explanation:
        context.explanation = "Result processed."

    # Generate final preview formats
    t_start_fmt = time.time()
    result_preview_str = ""
    result_file_path = None
    has_chart = os.path.exists(chart_html_path)
    active_chart_id = chart_uuid if has_chart else None
    
    if isinstance(result, pd.DataFrame):
        # Cap result rows
        if dataset_rows > 10000:
            result = result.head(10000)
            dataset_rows = 10000
            
        for col in result.columns:
            if pd.api.types.is_datetime64_any_dtype(result[col]):
                result[col] = result[col].astype(str)
                
        if dataset_rows > 100:
            # Save file in Parquet format in results dir
            os.makedirs(RESULTS_DIR, exist_ok=True)
            parquet_filename = f"{str(uuid.uuid4())}.parquet"
            result_file_path = os.path.join(RESULTS_DIR, parquet_filename)
            result.to_parquet(result_file_path)
            
            # Send first 50 rows, then stream next 50 (chunking)
            result_preview_str = json.dumps(result.head(100).to_dict(orient="records"))
        else:
            result_preview_str = json.dumps(result.to_dict(orient="records"))
    elif isinstance(result, pd.Series):
        series_dict = [{"Index": str(k), "Value": str(v)} for k, v in result.items()]
        result_preview_str = json.dumps(series_dict)
    else:
        result_preview_str = json.dumps([{"Result": str(result)}])

    timings["Formatting"] = time.time() - t_start_fmt
    
    t_start_ser = time.time()
    total_taken = time.time() - total_start
    timings["Response"] = total_taken
    
    # Calculate slowest stage dynamically
    max_val = -1.0
    slowest = "None"
    for stage, val in timings.items():
        if stage != "Response" and val > max_val:
            max_val = val
            slowest = stage
            
    # Compile debug breakdown
    debug_info = {
        "timings": {k: round(v, 4) for k, v in timings.items()},
        "complexity": complexity,
        "engine_used": engine_type,
        "prompt_size": context.prompt_size,
        "model": context.model,
        "cache_hit": False,
        "auto_retry_count": auto_retry_count,
        "router_decision": router_res,
        "slowest_stage": f"{slowest} ({max_val * 1000:.1f}ms)",
        "cache_used": False,
        "llm_used": True,
        "parser_used": False
    }
    
    debug_info_str = json.dumps(debug_info)
    timings["Serialization"] = time.time() - t_start_ser
    
    # Save cache
    cached_payload = {
        "status": "success",
        "dataset_id": dataset_id,
        "model": context.model,
        "rows": dataset_rows,
        "chart_id": active_chart_id,
        "result": json.loads(result_preview_str),
        "code": code,
        "explanation": context.explanation,
        "prompt_size": context.prompt_size,
        "engine_used": engine_type,
        "debug_info": debug_info
    }
    engine.set_cached_result(cache_key, cached_payload)
    
    # Queue background task to save db, summary, logs, cleanups
    background_tasks.add_task(
        background_tasks_worker,
        conv_id=conversation_id,
        user_msg_id=str(uuid.uuid4()),
        assistant_msg_id=assistant_msg_id,
        question=question,
        code=code,
        result_preview_str=result_preview_str,
        result_file_path=result_file_path,
        chart_id=active_chart_id,
        explanation=context.explanation,
        time_taken=total_taken,
        dataset_rows=dataset_rows,
        prompt_size=context.prompt_size,
        engine_used=engine_type,
        debug_info_str=debug_info_str,
        chart_png_path=chart_png_path,
        chart_html_path=chart_html_path,
        chart_meta_path=chart_meta_path,
        dataset_id=dataset_id
    )

    # Yield success payload
    final_payload = {
        "type": "success",
        "status": "success",
        "conversation_id": conversation_id,
        "dataset_id": dataset_id,
        "model": context.model,
        "execution_time": round(total_taken, 3),
        "rows": dataset_rows,
        "chart_id": active_chart_id,
        "result": json.loads(result_preview_str),
        "code": code,
        "explanation": context.explanation,
        "prompt_size": context.prompt_size,
        "engine_used": engine_type,
        "debug_info": debug_info
    }
    yield json.dumps(final_payload) + "\n"

@router.post("/query")
def run_query(req: QueryRequest, background_tasks: BackgroundTasks):
    """
    POST route returning a StreamingResponse that sends SSE chunks of progress updates and final query results.
    """
    return StreamingResponse(
        execute_query_stream(req, background_tasks),
        media_type="text/event-stream"
    )

@router.get("/conversations")
def get_conversations():
    return db.list_conversations()

@router.get("/conversations/search")
def search_conversations(q: str):
    return db.search_conversations(q)

@router.get("/conversation/{id}")
def get_conversation_details(id: str):
    conv = db.get_conversation(id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = db.get_messages(id, limit=None)
    # Parse results and debug breakdown
    for msg in messages:
        if msg.get("result_preview"):
            try:
                msg["result"] = json.loads(msg["result_preview"])
            except Exception:
                msg["result"] = []
        else:
            msg["result"] = []
            
        if msg.get("debug_info"):
            try:
                msg["debug_info"] = json.loads(msg["debug_info"])
            except Exception:
                msg["debug_info"] = None
    return {
        "conversation": conv,
        "messages": messages
    }

@router.delete("/conversation/{id}")
def delete_conversation_api(id: str):
    db.delete_conversation(id)
    return {"status": "success", "message": "Conversation deleted."}

@router.get("/chart/html")
def get_chart_html(id: str | None = None):
    if id:
        safe_id = os.path.basename(id)
        path = os.path.join(CHARTS_DIR, f"{safe_id}.html")
        if os.path.exists(path):
            return FileResponse(path, media_type="text/html")
    raise HTTPException(status_code=404, detail="No interactive chart available.")

@router.get("/chart/png")
def get_chart_png(id: str | None = None):
    if id:
        safe_id = os.path.basename(id)
        path = os.path.join(CHARTS_DIR, f"{safe_id}.png")
        if not os.path.exists(path):
            import backend.services.chart_factory as cf
            cf.generate_png_on_demand(CHARTS_DIR, safe_id)
        if os.path.exists(path):
            return FileResponse(path, media_type="image/png")
    raise HTTPException(status_code=404, detail="No static chart available.")
