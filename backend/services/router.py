import re
import backend.config as config
from backend.services.kpi_engine import is_kpi_dashboard_query

# Engine Keywords Mapping
ENGINE_KEYWORDS = {
    "insight": {"insight", "hidden", "analysis", "trend", "pattern", "business", "key finding", "observation", "summary", "findings", "anomalies", "pareto", "abc"},
    "visualization": {"chart", "graph", "plot", "pie", "bar", "line", "histogram", "scatter", "dashboard", "treemap", "box plot"},
    "prediction": {"predict", "forecast", "trend", "extrapolate", "growth"},
    "explanation": {"explain", "why", "interpretation", "what does this mean"},
    "metadata": {"how many tables", "show tables", "describe table", "columns", "schema", "dataset info", "list tables"},
    "aggregation": {"average", "mean", "sum", "count", "max", "min", "median", "total", "group by", "highest", "lowest", "most", "least"},
    "filter": {"show", "list", "find", "display", "give me", "only", "where", "whose", "having", "equal", "greater", "less", "between", "after", "before", "contains", "starts with", "ends with", "joined", "hire", "latest", "newest", "oldest", "year", "month", "day", "recent"},
    "general_chat": {"hello", "hi", "hey", "greetings", "thanks", "thank you", "who are you", "what can you do", "joke", "help", "capabilities"}
}

ANALYTICS_LIB_KEYWORDS = {
    "cagr", "yoy", "qoq", "mom", "growth", "pareto", "abc", "anomaly", "anomalies", 
    "outlier", "outliers", "running total", "moving average", "rolling window", "percentile"
}

def detect_complexity(question: str) -> str:
    """
    Heuristic rule-based complexity detector. Returns 'complex' or 'simple'.
    """
    question_lower = question.lower()
    agg_matches = len(re.findall(r"\b(average|mean|sum|max|min|count|total|median)\b", question_lower))
    has_join = any(word in question_lower for word in ["join", "merge", "combine", "together", "relationships"])
    has_forecast = any(word in question_lower for word in ["forecast", "predict", "trend", "extrapolate", "growth"])
    has_dashboard = "dashboard" in question_lower
    
    if has_join or has_forecast or has_dashboard or agg_matches >= 2:
        return "complex"
    return "simple"

def classify_query_engine_detailed(question: str, prev_plan: dict = None, conversation_id: str = None) -> dict:
    """
    Hierarchical cost-based planner and router.
    Resolves query target based on complexity, confidence, and local capability.
    """
    from backend.services.query_parser import parse_question
    
    # Retrieve active dataset
    active_df = None
    active_df_name = ""
    if config.datasets:
        active_df_name = list(config.datasets.keys())[0]
        active_df = config.datasets[active_df_name]
        
    # Execute parser
    parsed = parse_question(question, active_df, active_df_name, prev_plan=prev_plan, conversation_id=conversation_id)
    
    # Determine the cheapest engine that can solve this query
    engine_selected = "deterministic"
    llm_used = False
    cost = 0.2  # Base cost of local deterministic engine
    fallback_reason = None
    
    q_lower = question.lower()
    
    # 1. Metadata Engine
    if parsed.intent == "metadata":
        engine_selected = "metadata"
        cost = 0.1
    # 2. General Chat
    elif parsed.intent == "general_chat":
        engine_selected = "general_chat"
        cost = 0.1
    # 3. KPI Dashboard
    elif is_kpi_dashboard_query(question):
        engine_selected = "kpi_dashboard"
        cost = 0.1
    # 4. ID Lookup
    elif parsed.intent == "id_lookup":
        engine_selected = "id_lookup"
        cost = 0.2
    # 5. Advanced Analytics Library
    elif any(kw in q_lower for kw in ANALYTICS_LIB_KEYWORDS):
        engine_selected = "analytics_lib"
        cost = 0.3
    # 6. Visualization
    elif parsed.intent == "visualization":
        engine_selected = "visualization"
        cost = 0.5
    # 7. SQL or LLM fallback
    else:
        # Check confidence
        if parsed.confidence < 0.70:
            llm_used = True
            cost = 2.0  # High cost of LLM invocation
            if "forecast" in q_lower or "predict" in q_lower:
                engine_selected = "prediction"
                fallback_reason = "Forecasting/Prediction request requires LLM Planner."
            elif config.current_source_type == "sql" and config.database_engine:
                engine_selected = "sql"
                fallback_reason = "SQL database engine requires LLM translation."
            else:
                engine_selected = "llm"
                fallback_reason = f"Confidence score {parsed.confidence:.2f} is below threshold 0.70."
        else:
            engine_selected = "deterministic"
            cost = 0.2

    # Matched categories/values
    matched_values = list(parsed.entities.get("matched_categorical", {}).values())
    
    matched_keywords = []
    for engine_name, keywords in ENGINE_KEYWORDS.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', q_lower):
                matched_keywords.append(kw)
                
    return {
        "engine": engine_selected,
        "confidence": parsed.confidence,
        "matched_columns": parsed.entities.get("matched_columns", []),
        "matched_values": matched_values,
        "matched_keywords": list(set(matched_keywords)),
        "fallback_reason": fallback_reason,
        "llm_used": llm_used,
        "execution_cost": cost,
        "parsed_query": parsed
    }
