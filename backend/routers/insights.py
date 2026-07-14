import json
from fastapi import APIRouter
import backend.config as config
from backend.services.llm import call_llm
from backend.services.schema_cache import get_table_schema

router = APIRouter(prefix="/api")

@router.get("/insights")
def get_insights():
    """
    Constructs high-value insights by reading database schema details directly from cache.
    """
    available_sources = []
    if config.current_source_type == "sql" and config.database_engine:
        try:
            from sqlalchemy import inspect
            inspector = inspect(config.database_engine)
            available_sources = inspector.get_table_names()
        except Exception:
            pass
    else:
        available_sources = list(config.datasets.keys())
        
    schema_info = ""
    for name in available_sources:
        schema_info += get_table_schema(name) + "\n"
            
    if not schema_info.strip():
        return {"insights": [], "message": "No data source loaded."}
        
    prompt = f"""
You are an expert Chief Data Officer and AI Data Analyst.
Here are the schemas and metadata of the currently loaded data sources:

{schema_info}

Based on these datasets/tables, generate 4 high-value, strategic, and detailed AI-driven business insights or analysis ideas.
Format your output as a JSON list of objects. Each object must have the following keys:
1. "title": A concise, action-oriented title for the insight.
2. "metric": A key performance indicator or metric name relevant to this insight.
3. "description": A paragraph describing what the insight means, why it matters, and how it can be analyzed.
4. "sql_or_python": A sample SQL query or Pandas snippet to perform the analysis.

Return ONLY valid JSON (no markdown block, no extra characters, just the raw JSON list).
"""
    try:
        response_text = call_llm(prompt)
        # Parse JSON
        clean_json = response_text.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        clean_json = clean_json.strip()
        
        insights = json.loads(clean_json)
        return {"insights": insights}
    except Exception as e:
        # Fallback
        return {
            "insights": [
                {
                    "title": "Revenue Performance Trends",
                    "metric": "Sales Growth",
                    "description": "Analyze sales and order figures to determine growth patterns, identify the highest value transactions, and spot seasonal deviations.",
                    "sql_or_python": "df.groupby('date')['sales'].sum()"
                },
                {
                    "title": "Data Distribution Insights",
                    "metric": "Anomaly Detection",
                    "description": "Scan data ranges to detect outliers or records that deviate significantly from average values, indicating data errors or unique anomalies.",
                    "sql_or_python": "df[df['sales'] > df['sales'].mean() + 3*df['sales'].std()]"
                }
            ],
            "error": str(e)
        }
