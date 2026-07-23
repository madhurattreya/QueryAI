The previous generated code/query failed with the following execution error:
{error_msg}

Here is the code/query that failed:
{failed_code}

Here is the schema/profile:
{schema_desc}
{profile_desc}

Please generate a corrected version of the code/query.
Rules:
1. Fix any column reference errors. You MUST ONLY reference column names listed in the schema/profile above.
2. CRITICAL CONCEPT-TO-COLUMN MAPPING: If the previous code failed because it referenced a title/phrase like 'Regional Sales Performance', 'Category-wise Revenue', 'Monthly Sales Trend', or 'Top 5 Salesperson':
   - Recognize that these phrases are query titles or business concepts, NOT actual dataset column names!
   - Map the concept to actual schema columns (e.g. 'Regional Sales Performance' -> Region & Sales; 'Category-wise Revenue' -> Category & Sales/Revenue).
   - Perform the required aggregation first: `df_chart = df.groupby('Region')['Sales'].sum().reset_index()`.
   - Never index a DataFrame using a non-existent phrase as a column name.
3. Fix any syntax or runtime errors.
4. Output ONLY the corrected code block (```python ... ``` or ```sql ... ```). Do not write explanations.
5. Set the final result to the variable 'result' (for Python) or write a single SELECT query (for SQL).
