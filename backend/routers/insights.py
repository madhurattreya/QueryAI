"""
backend/routers/insights.py
─────────────────────────────
FastAPI Router for AI Business Insights generation.
"""

import json
import logging
import pandas as pd
from fastapi import APIRouter
import backend.config as config
from backend.services.llm import LLMManager
from backend.services.schema_cache import get_table_schema


logger = logging.getLogger("queryiq.insights")
router = APIRouter(prefix="/api", tags=["Insights"])

@router.get("/insights")
def get_insights():
    """
    Generates high-value strategic business insights by analyzing dataset schemas.
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
        return {
            "status": "empty",
            "insights": [],
            "message": "No active dataset loaded for insights analysis."
        }
        
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
        manager = LLMManager()
        response_text, _, _ = manager.call_llm_with_fallback(prompt, model=config.settings.get("model", "qwen2.5:3b"))
        
        # Parse JSON output
        clean_json = response_text.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        if clean_json.startswith("```"):
            clean_json = clean_json[3:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        clean_json = clean_json.strip()
        
        insights = json.loads(clean_json)
        return {"status": "success", "insights": insights}
        
    except Exception as e:
        logger.error(f"LLM insights generation failed: {e}. Returning rule-based fallback insights.")
        # Programmatic / Rule-based Fallback Insights
        first_ds = available_sources[0] if available_sources else "Dataset"
        df = config.datasets.get(first_ds) if available_sources else None
        
        cols = list(df.columns) if df is not None else ["date", "sales", "category", "region"]
        num_cols = [c for c in cols if df is not None and pd.api.types.is_numeric_dtype(df[c])] if df is not None else ["sales", "profit"]
        cat_cols = [c for c in cols if c not in num_cols] if df is not None else ["category", "region"]
        
        metric_col = num_cols[0] if num_cols else "Total Value"
        group_col = cat_cols[0] if cat_cols else "Category"
        
        return {
            "status": "success",
            "insights": [
                {
                    "title": f"Concentration Analysis by {group_col}",
                    "metric": "Pareto Distribution",
                    "description": f"Analyze distribution of {metric_col} across {group_col} groups to discover top revenue drivers and tail risk concentrations.",
                    "sql_or_python": f"df.groupby('{group_col}')['{metric_col}'].sum().sort_values(ascending=False)"
                },
                {
                    "title": f"Statistical Outlier & Anomaly Detection",
                    "metric": "3-Sigma Volatility",
                    "description": f"Scan numeric distribution of {metric_col} to identify records deviating > 3 standard deviations from average values.",
                    "sql_or_python": f"df[df['{metric_col}'] > df['{metric_col}'].mean() + 3 * df['{metric_col}'].std()]"
                },
                {
                    "title": f"Summary Statistics & Variance Check",
                    "metric": "Coefficient of Variation",
                    "description": f"Evaluate volatility, percentiles, mean vs median skewness across primary numeric measures.",
                    "sql_or_python": f"df[['{metric_col}']].describe()"
                },
                {
                    "title": f"Multi-Dimension Metric Aggregation",
                    "metric": "Group Performance",
                    "description": f"Compute aggregated sums and averages partitioned across categorical dimensions for comparative benchmarking.",
                    "sql_or_python": f"df.groupby(['{group_col}'])['{metric_col}'].agg(['sum', 'mean', 'count'])"
                }
            ],
            "fallback": True
        }
