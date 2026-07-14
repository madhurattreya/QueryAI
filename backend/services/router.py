import re
import backend.config as config
from backend.services.llm import LLMManager

# Engine Keywords Mapping
ENGINE_KEYWORDS = {
    "insight": {"insight", "hidden", "analysis", "trend", "pattern", "business", "key finding", "observation", "summary", "findings"},
    "visualization": {"chart", "graph", "plot", "pie", "bar", "line", "histogram", "scatter", "dashboard"},
    "prediction": {"predict", "forecast", "trend", "extrapolate", "machine learning"},
    "explanation": {"explain", "why", "interpretation", "what does this mean"},
    "metadata": {"how many tables", "show tables", "describe table", "columns", "schema", "dataset info", "list tables"},
    "aggregation": {"average", "mean", "sum", "count", "max", "min", "median", "total", "group by", "highest", "lowest", "most", "least"},
    "filter": {"show", "list", "find", "display", "give me", "only", "where", "whose", "having", "equal", "greater", "less", "between", "after", "before", "contains", "starts with", "ends with", "joined", "hire", "latest", "newest", "oldest", "year", "month", "day", "recent"},
    "general_chat": {"hello", "hi", "hey", "greetings", "thanks", "thank you", "who are you", "what can you do", "joke", "help", "capabilities"}
}

def detect_complexity(question: str) -> str:
    """
    Heuristic rule-based complexity detector. Returns 'complex' or 'simple'.
    """
    question_lower = question.lower()
    
    # Check for multi-aggregation or multiple metrics
    agg_matches = len(re.findall(r"\b(average|mean|sum|max|min|count|total|median)\b", question_lower))
    
    # Check for join indicators
    has_join = any(word in question_lower for word in ["join", "merge", "combine", "together", "relationships"])
    
    # Check for forecasting / multi-stage math
    has_forecast = any(word in question_lower for word in ["forecast", "predict", "trend", "extrapolate", "growth"])
    
    # Check for dashboard request
    has_dashboard = "dashboard" in question_lower
    
    if has_join or has_forecast or has_dashboard or agg_matches >= 2:
        return "complex"
    return "simple"

def get_known_schema_elements() -> tuple:
    """
    Extracts all loaded table names and column names from cache and config.
    """
    known_tables = []
    known_columns = []
    
    # 1. From Pandas datasets
    for table_name, df in config.datasets.items():
        known_tables.append(table_name.lower())
        known_columns.extend([col.lower() for col in df.columns])
        
    # 2. From SQL database
    if config.current_source_type == "sql" and config.database_engine:
        try:
            from sqlalchemy import inspect
            inspector = inspect(config.database_engine)
            for t in inspector.get_table_names():
                known_tables.append(t.lower())
                known_columns.extend([col["name"].lower() for col in inspector.get_columns(t)])
        except Exception:
            pass
            
    return set(known_tables), set(known_columns)

def classify_query_engine_detailed(question: str) -> dict:
    """
    Categorizes the query using the deterministic query parser and falls back if needed.
    """
    from backend.services.query_parser import parse_question
    
    # Retrieve active dataset
    active_df = None
    active_df_name = ""
    if config.datasets:
        active_df_name = list(config.datasets.keys())[0]
        active_df = config.datasets[active_df_name]
        
    # Execute parser
    parsed = parse_question(question, active_df, active_df_name)
    
    # Determine fallback and telemetry
    fallback_reason = None
    llm_used = False
    
    if parsed.confidence < 0.90:
        llm_used = True
        if "forecast" in question.lower() or "predict" in question.lower():
            fallback_reason = "Forecasting/Prediction request requires Planner + LLM."
        elif len(parsed.filters) > 3 or len(parsed.aggregations) > 2:
            fallback_reason = "Complex query with multiple aggregations/filters."
        else:
            fallback_reason = f"Confidence score {parsed.confidence:.2f} is below deterministic threshold 0.90."
            
    # Extract matched categorical values list for telemetry
    matched_values = list(parsed.entities.get("matched_categorical", {}).values())
    
    # Matched keywords
    matched_keywords = []
    for engine_name, keywords in ENGINE_KEYWORDS.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', question.lower()):
                matched_keywords.append(kw)
                
    return {
        "engine": parsed.intent,
        "confidence": parsed.confidence,
        "matched_columns": parsed.entities.get("matched_columns", []),
        "matched_values": matched_values,
        "matched_keywords": list(set(matched_keywords)),
        "fallback_reason": fallback_reason,
        "llm_used": llm_used,
        "parsed_query": parsed
    }

def classify_query_engine(question: str, current_source_type: str, has_sql_conn: bool) -> str:
    res = classify_query_engine_detailed(question)
    return res["engine"]

def select_relevant_sources(question: str, available_sources: list) -> list:
    """
    Prunes the schema to only include relevant source tables, preventing prompt bloat.
    """
    if len(available_sources) <= 1:
        return available_sources

    # Check for direct keyword matches first (fast path)
    matched_sources = []
    question_lower = question.lower()
    for source in available_sources:
        source_base = source.lower().rstrip('s')
        if source.lower() in question_lower or (len(source_base) > 2 and source_base in question_lower):
            matched_sources.append(source)
            
    if matched_sources:
        return matched_sources

    # Fallback to LLM selector
    sources_str = ", ".join(available_sources)
    prompt = f"""
You are a database router.
Your job is to read the user's question and select ONLY the relevant table/dataset names from the available list that are required to answer the question.

Available datasets/tables:
{sources_str}

Rules:
1. Return ONLY a comma-separated list of selected dataset/table names (e.g. "customers, orders").
2. Do not include any explanations, introduction, markdown blocks, or other text.
3. If you are unsure, list them all.
4. Only select names that exist in the list above.

Question:
{question}
"""
    try:
        model = config.settings.get("model", "qwen2.5:7b")
        manager = LLMManager()
        content, _ = manager.call_llm_with_fallback(prompt, model)
        content = content.strip()
        content = re.sub(r'[^a-zA-Z0-9_,\s]', '', content)
        selected = [name.strip() for name in content.split(",") if name.strip()]
        valid_selected = [name for name in selected if name in available_sources]
        
        if not valid_selected:
            return available_sources
        return valid_selected
    except Exception:
        return available_sources
