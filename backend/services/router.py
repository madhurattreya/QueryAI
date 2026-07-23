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
    Wires the new QueryPlanner for fast deterministic execution & fuzzy column recovery.
    """
    from backend.services.query_planner import QueryPlanner
    from backend.services.query_parser import ParsedQuery, parse_question
    from backend.models.execution_plan import EngineType, IntentType
    
    q_lower = question.lower()
    if ("create" in q_lower or "generate" in q_lower or "build" in q_lower or "make" in q_lower) and "dashboard" in q_lower:
        return {
            "engine": "dashboard_gen",
            "cost": 1.0,
            "llm_used": False,
            "complexity": detect_complexity(question),
            "confidence": 0.98,
            "parsed_query": None,
            "fallback_used": False,
            "fallback_reason": None
        }

    # ─── New Phase B QueryPlanner Integration ──────────────────────────────
    active_df_name = list(config.datasets.keys())[0] if config.datasets else None
    active_df = config.datasets[active_df_name] if active_df_name and active_df_name in config.datasets else None
    planner = QueryPlanner(active_df_name)
    plan = planner.plan(question)
    
    # Check if we can intercept with deterministic query engine
    is_det_eligible = (
        plan.confidence >= config.app_settings.confidence_threshold_deterministic or
        plan.engine_type in [EngineType.GENERAL_CHAT, EngineType.KPI_DASHBOARD, EngineType.METADATA]
    )
    
    if is_det_eligible:
        # Check validation errors
        has_val_errors = plan.validation_result and plan.validation_result.has_errors
        
        if not has_val_errors:
            # Reconstruct legacy ParsedQuery using resolved/recovered columns
            # Apply warnings/suggestions to filters/aggregations
            filters_legacy = []
            for f in plan.filters:
                # Patch corrected name if resolved via resolver
                col_name = f.column
                res = plan.column_resolution.get(f.column)
                if res and res.is_resolved and res.resolved_column:
                    col_name = res.resolved_column
                filters_legacy.append({"column": col_name, "operator": f.operator, "value": f.value})
                
            aggs_legacy = []
            for a in plan.aggregations:
                col_name = a.column
                res = plan.column_resolution.get(a.column)
                if res and res.is_resolved and res.resolved_column:
                    col_name = res.resolved_column
                aggs_legacy.append({"column": col_name, "operator": a.operator})
                
            sorts_legacy = []
            for s in plan.sorting:
                col_name = s.column
                res = plan.column_resolution.get(s.column)
                if res and res.is_resolved and res.resolved_column:
                    col_name = res.resolved_column
                sorts_legacy.append({"column": col_name, "ascending": s.ascending})
                
            cols_legacy = []
            for c in plan.selected_columns:
                res = plan.column_resolution.get(c)
                if res and res.is_resolved and res.resolved_column:
                    cols_legacy.append(res.resolved_column)
                else:
                    cols_legacy.append(c)

            # Map engine types to legacy engine strings
            legacy_engine = "deterministic"
            if plan.engine_type == EngineType.METADATA:
                legacy_engine = "metadata"
            elif plan.engine_type == EngineType.GENERAL_CHAT:
                legacy_engine = "general_chat"
            elif plan.engine_type == EngineType.KPI_DASHBOARD:
                legacy_engine = "kpi_dashboard"
            elif plan.engine_type == EngineType.AMBIGUITY:
                legacy_engine = "ambiguity"
                
            parsed = ParsedQuery(
                intent=plan.intent.value,
                confidence=plan.confidence,
                filters=filters_legacy,
                aggregations=aggs_legacy,
                sorting=sorts_legacy,
                chart_type=plan.intent.value if plan.intent == IntentType.VISUALIZATION else None,
                execution_plan={
                    "intent": plan.intent.value,
                    "groupby": plan.groupby,
                    "limit": plan.limit,
                    "question": question,
                    "matched_columns": cols_legacy,
                    "measure": aggs_legacy[0]["column"] if aggs_legacy else "result",
                },
                entities={
                    "matched_columns": cols_legacy,
                    "matched_categorical": {}
                }
            )
            
            # Map parameters for telemetry logs
            matched_values = []
            matched_keywords = [plan.intent.value]
            
            print(f"[API QUERY] Deterministic route intercepted: intent={plan.intent.value}, engine={legacy_engine}")
            return {
                "engine": legacy_engine,
                "confidence": plan.confidence,
                "matched_columns": cols_legacy,
                "matched_values": matched_values,
                "matched_keywords": matched_keywords,
                "fallback_reason": None,
                "llm_used": False,
                "execution_cost": 0.1,
                "fallback_used": False,
                "parsed_query": parsed
            }
            
    # ─── Legacy Fallback ──────────────────────────────────────────────────
    # Execute parser
    parsed = parse_question(question, active_df, active_df_name, prev_plan=prev_plan, conversation_id=conversation_id)
    
    # Determine the cheapest engine that can solve this query
    engine_selected = "deterministic"
    llm_used = False
    cost = 0.2  # Base cost of local deterministic engine
    fallback_reason = None
    
    q_lower = question.lower()
    
    # 0.5. Dashboard Generation
    if ("create" in q_lower or "generate" in q_lower or "build" in q_lower or "make" in q_lower) and "dashboard" in q_lower:
        engine_selected = "dashboard_gen"
        cost = 1.0
        llm_used = True
        
    # 1. Metadata Engine
    elif parsed.intent == "metadata":
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
    # 6.5. Ambiguity check
    elif parsed.intent == "ambiguity":
        engine_selected = "ambiguity"
        cost = 0.1
        llm_used = False
    # 7. SQL or LLM fallback
    else:
        # Standardized confidence thresholds
        if parsed.confidence >= 0.90:
            engine_selected = "deterministic"
            cost = 0.2
            llm_used = False
        elif 0.75 <= parsed.confidence < 0.90:
            engine_selected = "deterministic"
            cost = 0.2
            llm_used = False
        else:
            if parsed.confidence < config.app_settings.confidence_threshold_hybrid:
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
                    fallback_reason = f"Confidence score {parsed.confidence:.2f} is below hybrid threshold."
            else:
                # Under 75 confidence for deterministic fallback maps to ambiguity
                engine_selected = "ambiguity"
                parsed.intent = "ambiguity"
                cost = 0.1
                llm_used = False

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
        "fallback_used": True,
        "parsed_query": parsed
    }

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
        model = config.settings.get("model", config.app_settings.default_model)
        from backend.services.llm import LLMManager
        manager = LLMManager()
        content, _, _llm_metrics = manager.call_llm_with_fallback(prompt, model)
        content = content.strip()
        content = re.sub(r'[^a-zA-Z0-9_,\s]', '', content)
        selected = [name.strip() for name in content.split(",") if name.strip()]
        valid_selected = [name for name in selected if name in available_sources]
        
        if not valid_selected:
            return available_sources
        return valid_selected
    except Exception:
        return available_sources

