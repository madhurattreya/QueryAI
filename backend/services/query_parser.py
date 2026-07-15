import re
import uuid
import datetime
import pandas as pd
from dataclasses import dataclass, field
import backend.config as config
from backend.services.profiler import profile_dataset

_categorical_values_cache = {}

def clear_parser_cache():
    global _categorical_values_cache
    _categorical_values_cache.clear()

@dataclass
class ParsedQuery:
    intent: str
    confidence: float
    entities: dict = field(default_factory=dict)
    filters: list = field(default_factory=list)
    aggregations: list = field(default_factory=list)
    sorting: list = field(default_factory=list)
    ranking: list = field(default_factory=list)
    chart_type: str = None
    prediction: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    execution_plan: dict = field(default_factory=dict)

# Typo, abbreviation, and Hinglish mapping
COMMON_REWRITES = {
    r"\bprofitt\b": "profit",
    r"\bsalry\b": "salary",
    r"\bsale\b": "sales",
    r"\bdepartmant\b": "department",
    r"\bcustmer\b": "customer",
    r"\bexperiance\b": "experience",
    r"\bemployeid\b": "employee id",
    r"\bwho\s+sold\s+best\b": "which salesperson generated the highest sales",
    r"\bprofit\s+dikhao\b": "show total profit",
    r"\bsabse\s+jyada\s+sale\s+kis\s+city\s+me\s+hui\b": "which city has the highest sales",
    r"\bdelhi\s+ka\s+profit\s+dikhao\b": "show profit in delhi",
    r"\bkitna\s+sale\s+hua\b": "show total sales",
}

def rewrite_query(question: str) -> str:
    q = question.lower().strip()
    for pattern, replacement in COMMON_REWRITES.items():
        q = re.sub(pattern, replacement, q)
    return q

def get_semantic_layer(df_name: str, df: pd.DataFrame) -> dict:
    """
    Loads Semantic Layer profile from cached profiler and merges custom SQLite semantic layer entries.
    """
    try:
        profile_str = profile_dataset(df_name, df)
        import json
        profile = json.loads(profile_str)
        sem_layer = profile.get("semantic_layer", {})
        
        # Merge SQLite custom semantic model entries
        try:
            from backend.services.semantic_model import SemanticModelManager
            import backend.services.history_db as db
            
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM datasets WHERE name = ? LIMIT 1", (df_name,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                dataset_id = row["id"]
                custom_items = SemanticModelManager().get_model_items(dataset_id)
                for item in custom_items:
                    col_name = item["name"]
                    # Map properties from SQLite record to the semantic entry
                    sem_layer[col_name] = {
                        "display_name": item.get("display_name") or item.get("name", col_name),
                        "description": item.get("description") or item.get("definition", ""),
                        "business_meaning": item.get("business_meaning") or "",
                        "synonyms": [s.strip() for s in (item.get("synonyms") or "").split(",") if s.strip()] if isinstance(item.get("synonyms"), str) else (item.get("synonyms") or []),
                        "units": item.get("units") or "units",
                        "aggregation_type": item.get("aggregation") or "sum",
                        "category": item.get("category") or ("Measure" if item.get("is_measure") == 1 else "Dimension"),
                        "hierarchy": item.get("hierarchy") or "",
                        "actual_column": col_name
                    }
        except Exception as e:
            print(f"[SEMANTIC LAYER WARNING] Failed to merge database semantic model: {e}")
            
        return sem_layer
    except Exception:
        return {}

def get_categorical_values(df_name: str, df: pd.DataFrame, col: str) -> set:
    cache_key = (df_name, col)
    if cache_key in _categorical_values_cache:
        return _categorical_values_cache[cache_key]
    
    val_set = set()
    is_text = (
        pd.api.types.is_string_dtype(df[col]) or 
        isinstance(df[col].dtype, pd.CategoricalDtype) or 
        df[col].dtype == 'object'
    )
    if is_text:
        try:
            if df[col].nunique() < 1000:
                val_set = {str(val).strip().lower() for val in df[col].dropna().unique() if str(val).strip()}
        except Exception:
            pass
    _categorical_values_cache[cache_key] = val_set
    return val_set

def compile_to_dsl(execution_plan: dict) -> dict:
    """
    Compiles query elements to Intermediate Analytics DSL.
    """
    dsl = {
        "filter": [],
        "group": execution_plan.get("groupby", []),
        "aggregate": [],
        "sort": [],
        "limit": execution_plan.get("limit"),
        "offset": execution_plan.get("offset", 0)
    }
    for filt in execution_plan.get("filters", []):
        dsl["filter"].append({
            "column": filt["column"],
            "operator": filt["operator"],
            "value": filt["value"]
        })
    for agg in execution_plan.get("aggregations", []):
        dsl["aggregate"].append({
            "column": agg["column"],
            "function": agg["operator"].upper()
        })
    for s in execution_plan.get("sorting", []):
        dsl["sort"].append({
            "column": s["column"],
            "direction": "ASC" if s["ascending"] else "DESC"
        })
    return dsl

def merge_conversational_context(current_plan: dict, prev_plan: dict, question: str, df: pd.DataFrame, conversation_id: str = None) -> dict:
    """
    Merges state memory from previous query's execution plan.
    """
    q_lower = question.lower()
    
    # 0. Undo / Go Back state retrieval
    if conversation_id and ("go back" in q_lower or "undo" in q_lower):
        try:
            import json
            import backend.services.history_db as db
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT debug_info FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY created_at DESC", (conversation_id,))
            rows = cursor.fetchall()
            conn.close()
            
            plans = []
            for r in rows:
                info_str = r["debug_info"]
                if info_str:
                    try:
                        info = json.loads(info_str)
                        if info.get("execution_plan"):
                            plans.append(info["execution_plan"])
                    except Exception:
                        pass
            if len(plans) > 1:
                return plans[1]
        except Exception as e:
            print(f"[UNDO WARNING] Failed to undo: {e}")

    if not prev_plan:
        return current_plan
        
    # Check for follow-up indicator keywords
    followup_words = ["only", "except", "exclude", "compare", "trend", "monthly", "quarterly", "second", "third", "next", "what about", "and", "then", "now show", "instead", "same for", "drill", "top", "bottom", "limit"]
    is_followup = any(w in q_lower for w in followup_words) or (len(current_plan.get("filters", [])) == 0 and len(current_plan.get("groupby", [])) == 0 and current_plan.get("intent") in ["lookup", "filter"])
    
    if not is_followup:
        return current_plan
        
    merged = prev_plan.copy()
    
    # 1. Offset limits (e.g. second highest, third lowest)
    if "second" in q_lower or "2nd" in q_lower:
        merged["offset"] = 1
        merged["limit"] = 1
        merged["intent"] = "aggregation" if prev_plan.get("groupby") else "filter"
    elif "third" in q_lower or "3rd" in q_lower:
        merged["offset"] = 2
        merged["limit"] = 1
        merged["intent"] = "aggregation" if prev_plan.get("groupby") else "filter"

    # 1.5. Same for [Year] / Year replacement (e.g. "same for 2024", "in 2024", "for 2024")
    year_match = re.search(r"\b(?:same\s+for|in|for)\s+(\d{4})\b", q_lower)
    if year_match:
        year_val = int(year_match.group(1))
        # Find any date column in df
        date_cols = [col for col in df.columns if "date" in col.lower() or "joined" in col.lower() or "hired" in col.lower() or "year" in col.lower()]
        if date_cols:
            date_col = date_cols[0]
            new_filter = {"column": date_col, "operator": "==", "value": year_val, "logical_relation": "and"}
            # Remove previous filters on this date column to avoid conflicts
            merged["filters"] = [f for f in merged.get("filters", []) if f["column"] != date_col] + [new_filter]

    # 1.6. Compare with previous year / YoY comparison
    if "previous year" in q_lower or "prior year" in q_lower or "yoy" in q_lower or "prev year" in q_lower:
        merged["intent"] = "analytics_lib"
        # Force YoY keyword in execution plan question
        merged["question"] = question + " yoy"
        
    # 2. Exclude filter (e.g. "excluding Delhi", "exclude furniture")
    exclude_match = re.search(r"\b(?:exclude|excluding|except)\s+([a-z0-9_\-\s]+)", q_lower)
    if exclude_match:
        val_to_exclude = exclude_match.group(1).strip()
        matched_col = None
        for col in df.columns:
            if df[col].dtype == 'object' or isinstance(df[col].dtype, pd.CategoricalDtype):
                if val_to_exclude in df[col].astype(str).str.lower().values:
                    matched_col = col
                    break
        if matched_col:
            new_filter = {"column": matched_col, "operator": "!=", "value": val_to_exclude, "logical_relation": "and"}
            merged["filters"] = [f for f in merged.get("filters", []) if f["column"] != matched_col or f["operator"] != "!="] + [new_filter]

    # 3. Only filter (e.g. "only furniture", "only West region")
    only_match = re.search(r"\bonly\s+([a-z0-9_\-\s]+)", q_lower)
    if only_match:
        val_only = only_match.group(1).strip()
        matched_col = None
        for col in df.columns:
            if df[col].dtype == 'object' or isinstance(df[col].dtype, pd.CategoricalDtype):
                if val_only in df[col].astype(str).str.lower().values:
                    matched_col = col
                    break
        if matched_col:
            new_filter = {"column": matched_col, "operator": "==", "value": val_only, "logical_relation": "and"}
            merged["filters"] = [f for f in merged.get("filters", []) if f["column"] != matched_col] + [new_filter]
            
    # 4. Compare with (e.g. "compare with Mumbai")
    compare_match = re.search(r"\bcompare\s+(?:with\s+)?([a-z0-9_\-\s]+)", q_lower)
    if compare_match:
        val_compare = compare_match.group(1).strip()
        matched_col = None
        for col in df.columns:
            if df[col].dtype == 'object' or isinstance(df[col].dtype, pd.CategoricalDtype):
                if val_compare in df[col].astype(str).str.lower().values:
                    matched_col = col
                    break
        if matched_col:
            prev_vals = [f["value"] for f in merged.get("filters", []) if f["column"] == matched_col and f["operator"] == "=="]
            if not prev_vals:
                # Check list/in filters
                prev_vals_list = [f["value"] for f in merged.get("filters", []) if f["column"] == matched_col and f["operator"] == "in"]
                if prev_vals_list:
                    prev_vals = prev_vals_list[0] if isinstance(prev_vals_list[0], list) else prev_vals_list
            if prev_vals:
                comparison_vals = (prev_vals if isinstance(prev_vals, list) else [prev_vals]) + [val_compare]
                new_filter = {"column": matched_col, "operator": "in", "value": comparison_vals, "logical_relation": "and"}
                merged["filters"] = [f for f in merged.get("filters", []) if f["column"] != matched_col] + [new_filter]
                merged["groupby"] = list(set(merged.get("groupby", []) + [matched_col]))

    # 5. What about filter replacement (e.g. "what about east")
    what_about_match = re.search(r"\bwhat\s+about\s+([a-z0-9_\-\s]+)", q_lower)
    if what_about_match:
        val_wa = what_about_match.group(1).strip()
        matched_col = None
        for col in df.columns:
            is_text_col = pd.api.types.is_string_dtype(df[col]) or isinstance(df[col].dtype, pd.CategoricalDtype) or df[col].dtype == 'object'
            if is_text_col:
                if val_wa in df[col].astype(str).str.lower().values:
                    matched_col = col
                    break
        if matched_col:
            new_filter = {"column": matched_col, "operator": "==", "value": val_wa, "logical_relation": "and"}
            merged["filters"] = [f for f in merged.get("filters", []) if f["column"] != matched_col] + [new_filter]

    # 6. Drill into / drill down (e.g. "drill into Delhi")
    drill_match = re.search(r"\bdrill\s+(?:into\s+)?([a-z0-9_\-\s]+)", q_lower)
    if drill_match:
        val_drill = drill_match.group(1).strip()
        matched_col = None
        for col in df.columns:
            is_text_col = pd.api.types.is_string_dtype(df[col]) or isinstance(df[col].dtype, pd.CategoricalDtype) or df[col].dtype == 'object'
            if is_text_col:
                if val_drill in df[col].astype(str).str.lower().values:
                    matched_col = col
                    break
        if matched_col:
            new_filter = {"column": matched_col, "operator": "==", "value": val_drill, "logical_relation": "and"}
            merged["filters"] = [f for f in merged.get("filters", []) if f["column"] != matched_col] + [new_filter]

    # 7. Drill down to grouping (e.g. "drill down to Category")
    drill_group_match = re.search(r"\bdrill\s+down\s+to\s+([a-z0-9_\-\s]+)", q_lower)
    if drill_group_match:
        group_col_name = drill_group_match.group(1).strip()
        matched_col = None
        for col in df.columns:
            if col.lower().replace(" ", "_") == group_col_name.lower().replace(" ", "_"):
                matched_col = col
                break
        if matched_col:
            merged["groupby"] = list(set(merged.get("groupby", []) + [matched_col]))

    # 8. Top/Bottom overrides (e.g. "top 5")
    top_bottom_match = re.search(r"\b(top|bottom|highest|lowest)\s+(\d+)\b", q_lower)
    if top_bottom_match:
        limit_type = "bottom" if top_bottom_match.group(1) in ("bottom", "lowest") else "top"
        limit_val = int(top_bottom_match.group(2))
        merged["limit"] = limit_val
        merged["limit_type"] = limit_type

    # 9. Expand / Collapse
    if "expand" in q_lower:
        merged["limit"] = (merged.get("limit") or 10) * 2
    elif "collapse" in q_lower:
        merged["limit"] = max(1, int((merged.get("limit") or 10) / 2))

    # 9.5. Show details / Raw data (e.g. "show details", "details")
    if "show details" in q_lower or "show detail" in q_lower or "raw data" in q_lower:
        merged["groupby"] = []
        merged["limit"] = 100
        merged["intent"] = "lookup"

    # 10. Trend / Timeframe adjustments (e.g. "show monthly trend")
    if "trend" in q_lower or "monthly" in q_lower or "quarterly" in q_lower:
        date_cols = [col for col in df.columns if "date" in col.lower() or "joined" in col.lower() or "hired" in col.lower()]
        if date_cols:
            merged["groupby"] = [date_cols[0]]
            merged["chart_type"] = "line"
            merged["intent"] = "visualization"

    # Swap measures if asked (e.g. "now show sales")
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            if f"show {col.lower()}" in q_lower or f"sum of {col.lower()}" in q_lower or f"average of {col.lower()}" in q_lower:
                merged["aggregations"] = [{"column": col, "operator": "mean" if "average" in q_lower else "sum"}]
                merged["measure"] = col
                if merged.get("sorting"):
                    merged["sorting"] = [{"column": col, "ascending": merged["sorting"][0]["ascending"]}]
                    
    # Integrate current query's active filters
    if current_plan.get("filters"):
        current_cols = {f["column"] for f in current_plan["filters"]}
        merged["filters"] = [f for f in merged.get("filters", []) if f["column"] not in current_cols] + current_plan["filters"]
        
    return merged

def parse_question(question: str, active_df: pd.DataFrame = None, active_df_name: str = "", prev_plan: dict = None, conversation_id: str = None) -> ParsedQuery:
    """
    Parses natural language question dynamically into ParsedQuery execution plan.
    Target latency: < 5ms.
    """
    # 1. Pre-process Query rewrite
    q_rewritten = rewrite_query(question)
    q_norm = q_rewritten
    
    # Standardize formatting
    while re.search(r"\b(\d+),(\d+)\b", q_norm):
        q_norm = re.sub(r"\b(\d+),(\d+)\b", r"\1\2", q_norm)
        
    # 2. Semantic layer matching
    semantic_layer = {}
    cols_map = {}
    known_cols = []
    if active_df is not None:
        known_cols = active_df.columns.tolist()
        semantic_layer = get_semantic_layer(active_df_name, active_df)
        
        # Preprocess column names with spaces: replace spaces with underscores in the question
        for col in sorted(known_cols, key=len, reverse=True):
            col_space = col.lower().replace("_", " ")
            if " " in col_space:
                q_norm = re.sub(r"\b" + re.escape(col_space) + r"\b", col.lower().replace(" ", "_"), q_norm)
                
        for col in known_cols:
            cols_map[col.lower()] = col
            cols_map[col.lower().replace(" ", "_")] = col
            cols_map[col.lower().replace("_", " ")] = col

    q_clean = q_norm

    # Helper to resolve columns semantically
    def resolve_column(name: str) -> str:
        name_clean = name.strip().lower()
        
        # Look in semantic layer first
        matched_col = None
        max_match_len = 0
        for col, entry in semantic_layer.items():
            for synonym in entry.get("synonyms", []):
                syn_lower = synonym.lower()
                if syn_lower == name_clean or syn_lower in name_clean:
                    if len(syn_lower) > max_match_len:
                        matched_col = col
                        max_match_len = len(syn_lower)
        if matched_col:
            return matched_col
            
        if name_clean in cols_map:
            return cols_map[name_clean]
        # Try fuzzy match
        for k, v in cols_map.items():
            if name_clean in k or k in name_clean:
                return v
        return None

    # Intent heuristics
    intent = "lookup"
    confidence = 0.50
    match_reason = "Default lookup intent"
    
    # Check general chat
    chat_words = {"hello", "hi", "hey", "greetings", "thanks", "thank you", "who are you", "what can you do", "joke", "help", "capabilities"}
    words_in_q = set(re.findall(r"\b[a-z0-9_]+\b", q_rewritten))
    if words_in_q.intersection(chat_words) and not active_df_name:
        return ParsedQuery(intent="general_chat", confidence=0.95)
        
    # Detect viz/predict/insight/metadata keywords
    viz_keywords = {"chart", "graph", "plot", "pie", "bar", "line", "histogram", "scatter", "box", "heatmap", "area", "treemap", "dashboard"}
    has_viz = any(kw in q_rewritten for kw in viz_keywords)
    
    predict_keywords = {"predict", "forecast", "extrapolate", "growth", "prediction"}
    has_predict = any(kw in q_rewritten for kw in predict_keywords)
    
    insight_keywords = {"insight", "hidden", "analysis", "trend", "pattern", "business", "key finding", "observation", "summary"}
    has_insight = any(kw in q_rewritten for kw in insight_keywords)
    
    meta_keywords = {"how many tables", "show tables", "columns of", "describe table", "list tables", "schema", "dataset info"}
    has_meta = any(kw in q_rewritten for kw in meta_keywords)

    # Match columns mentioned in question
    matched_columns = []
    for col_orig in known_cols:
        col_lower = col_orig.lower()
        syns = [col_lower]
        if col_orig in semantic_layer:
            syns.extend(semantic_layer[col_orig].get("synonyms", []))
            
        for syn in syns:
            if re.search(r'\b' + re.escape(syn) + r'\b', q_rewritten) or re.search(r'\b' + re.escape(syn.replace(" ", "_")) + r'\b', q_rewritten):
                if col_orig not in matched_columns:
                    matched_columns.append(col_orig)

    # ID Lookup detection
    # "Order ID 132", "Customer 500", "Product ID 123"
    id_match = re.search(r"\b([a-z0-9_\-\s]+?)\s*(?:id)?\s*(\d+|[a-z]{1,2}\d+|\d{3,}\-[a-z0-9]+)\b", q_rewritten)
    id_lookup_target = None
    id_lookup_col = None
    if id_match:
        potential_col = resolve_column(id_match.group(1))
        if potential_col and ("id" in potential_col.lower() or "employee" in potential_col.lower() or "customer" in potential_col.lower() or "product" in potential_col.lower() or "order" in potential_col.lower()):
            id_lookup_col = potential_col
            id_lookup_target = id_match.group(2)
            intent = "id_lookup"
            confidence = 0.95
            match_reason = f"Detected ID lookup query targeting {id_lookup_col} with ID {id_lookup_target}."

    # Filters Extraction
    filters = []
    filter_placeholders = []
    
    # Null checking
    null_pattern = r"\b([a-z_0-9]+)\s+(?:is\s+)?(not\s+null|null|is\s+not\s+null|is\s+null)\b"
    for match in re.finditer(null_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op_text = match.group(2)
            op = "is_not_null" if "not" in op_text else "is_null"
            filt = {"column": col_name, "operator": op, "value": None}
            placeholder = f"__FP_NULL_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]
            
    # Range checks
    range_pattern = r"\b([a-z_0-9]+)\s+(?:is\s+)?(between|not\s+between)\s+['\"]?([a-z0-9_\-\.\/]+)['\"]?\s+and\s+['\"]?([a-z0-9_\-\.\/]+)['\"]?\b"
    for match in re.finditer(range_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op_text = match.group(2)
            op = "not between" if "not" in op_text else "between"
            val1, val2 = match.group(3), match.group(4)
            try: val1, val2 = float(val1), float(val2)
            except ValueError: pass
            filt = {"column": col_name, "operator": op, "value": [val1, val2]}
            placeholder = f"__FP_RANGE_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Lists
    list_pattern = r"\b([a-z_0-9]+)\s+(?:is\s+)?(in|not\s+in)\s*[\(\[]\s*([a-z0-9_\s'\",]+)\s*[\)\]]"
    for match in re.finditer(list_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op = match.group(2)
            raw_vals = match.group(3)
            vals = [v.strip().strip("'\"") for v in raw_vals.split(",") if v.strip()]
            parsed_vals = []
            for v in vals:
                try: parsed_vals.append(float(v) if '.' in v else int(v))
                except ValueError: parsed_vals.append(v)
            filt = {"column": col_name, "operator": op, "value": parsed_vals}
            placeholder = f"__FP_LIST_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Standard Comparisons
    text_comp_pattern = r"\b([a-z_0-9]+)\s+(?:is\s+|are\s+|was\s+)?(greater\s+than|less\s+than|above|below|equal\s+to|more\s+than)\s+['\"]?([a-z0-9_\-\.\/]+?)['\"]?(?=\s+(?:and|or|but|not|is|between|in)\b|$)"
    for match in re.finditer(text_comp_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op_cand = match.group(2)
            val_cand = match.group(3)
            try: val_cand = float(val_cand)
            except ValueError: pass
            op_map = {"greater than": ">", "above": ">", "more than": ">", "less than": "<", "below": "<", "equal to": "=="}
            filt = {"column": col_name, "operator": op_map.get(op_cand, "=="), "value": val_cand}
            placeholder = f"__FP_TXT_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    comp_pattern = r"\b([a-z_0-9]+)\s*(?:is\s+|are\s+|was\s+)?(>=|<=|>|<|!=|==|=)\s*['\"]?([a-z0-9_\-\.\/]+?)['\"]?(?=\s+(?:and|or|but|not|is|between|in)\b|$)"
    for match in re.finditer(comp_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op_cand = match.group(2)
            val_cand = match.group(3)
            try: val_cand = float(val_cand)
            except ValueError: pass
            op_map = {"=": "==", "==": "==", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<="}
            filt = {"column": col_name, "operator": op_map.get(op_cand, "=="), "value": val_cand}
            placeholder = f"__FP_SYM_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    is_pattern = r"\b([a-z_0-9]+)\s+(?:is|equal)\s+['\"]?([a-z0-9_\-\s\.\/]+?)['\"]?(?=\s+(?:and|or|but|not|is|between|in)\b|$)"
    for match in re.finditer(is_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            val_cand = match.group(2).strip()
            try: val_cand = float(val_cand)
            except ValueError: pass
            filt = {"column": col_name, "operator": "==", "value": val_cand}
            placeholder = f"__FP_IS_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Date / Time
    date_matches = re.finditer(r"\b(before|after|in|since|until)\s+(\d{4})\b", q_norm)
    for match in date_matches:
        op_cand = match.group(1)
        year_cand = int(match.group(2))
        date_cols = [c for c in matched_columns if "date" in c.lower() or "joined" in c.lower() or "hired" in c.lower()]
        if not date_cols and active_df is not None:
            date_cols = [c for c in known_cols if "date" in c.lower() or "joined" in c.lower() or "hired" in c.lower()]
        if date_cols:
            col = date_cols[0]
            if op_cand == "before": filt = {"column": col, "operator": "<", "value": f"{year_cand}-01-01"}
            elif op_cand in ("after", "since"): filt = {"column": col, "operator": ">", "value": f"{year_cand}-12-31"}
            elif op_cand == "in": filt = {"column": col, "operator": "between", "value": [f"{year_cand}-01-01", f"{year_cand}-12-31"]}
            else: filt = {"column": col, "operator": "<=", "value": f"{year_cand}-12-31"}
            placeholder = f"__FP_DATE_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Sort and collect filters
    filter_placeholders.sort(key=lambda x: x[0])
    for idx, (_, placeholder, filt) in enumerate(filter_placeholders):
        logical_relation = "and"
        if idx > 0:
            prev_end = filter_placeholders[idx-1][0]
            curr_start = filter_placeholders[idx][0]
            between_text = q_norm[prev_end:curr_start].lower()
            if "or" in re.findall(r"\b(or|but)\b", between_text):
                logical_relation = "or"
        filt_copy = filt.copy()
        filt_copy["logical_relation"] = logical_relation
        filters.append(filt_copy)

    # Categorical Implicit Matches
    matched_categorical = {}
    explicit_filtered_cols = {f["column"].lower() for f in filters}
    if active_df is not None and active_df_name:
        for col in known_cols:
            if col.lower() in explicit_filtered_cols: continue
            vals = get_categorical_values(active_df_name, active_df, col)
            if vals:
                for val in vals:
                    if re.search(r'\b' + re.escape(val) + r'\b', q_rewritten):
                        matched_categorical[col] = val
                        
    for col, val in matched_categorical.items():
        orig_val = val
        if active_df is not None:
            matches = active_df[active_df[col].astype(str).str.lower() == val]
            if not matches.empty:
                orig_val = matches[col].iloc[0]
        filters.append({"column": col, "operator": "==", "value": orig_val, "logical_relation": "and"})

    # Aggregation detection
    aggregations = []
    agg_keywords = {
        "average": "mean", "mean": "mean", "avg": "mean", "sum": "sum", "total": "sum",
        "count": "count", "max": "max", "min": "min", "highest": "max",
        "lowest": "min", "median": "median", "std": "std", "variance": "var",
        "percentile": "quantile"
    }
    for kw, op in agg_keywords.items():
        if re.search(r'\b' + re.escape(kw) + r'\b', q_rewritten):
            target_col = None
            numeric_ops = {"sum", "mean", "median", "std", "var", "quantile"}
            if op in numeric_ops and active_df is not None:
                numeric_matched = [c for c in matched_columns if pd.api.types.is_numeric_dtype(active_df[c])]
                if numeric_matched:
                    target_col = numeric_matched[0]
            if not target_col:
                target_col = matched_columns[0] if matched_columns else None
            if op == "count" and not target_col:
                target_col = known_cols[0] if known_cols else None
            if target_col:
                if not any(a["column"] == target_col and a["operator"] == op for a in aggregations):
                    aggregations.append({"column": target_col, "operator": op})

    # Group By Detection
    groupby_cols = []
    if "by" in q_rewritten or "wise" in q_rewritten:
        for col in known_cols:
            col_l = col.lower()
            if f"by {col_l}" in q_rewritten or f"{col_l}-wise" in q_rewritten or f"{col_l} wise" in q_rewritten:
                groupby_cols.append(col)

    # Smart Aggregation Planner (Implicit groupby + measure + rank detection)
    # E.g. "Which city has most profit", "highest sales region"
    if active_df is not None and not groupby_cols:
        # Find if we have a categorical column AND a measure column
        cat_cols = [c for c in matched_columns if active_df[c].dtype == 'object' or isinstance(active_df[c].dtype, pd.CategoricalDtype)]
        measure_cols = [c for c in matched_columns if pd.api.types.is_numeric_dtype(active_df[c])]
        
        # Check superlatives / extreme intents
        has_extreme = any(ex in q_rewritten for ex in ["most", "least", "highest", "lowest", "best", "worst", "top", "bottom"])
        if cat_cols and measure_cols and (has_extreme or aggregations):
            groupby_cols = [cat_cols[0]]
            if not aggregations:
                # Default sum aggregation for metrics
                aggregations.append({"column": measure_cols[0], "operator": "sum"})
            match_reason = f"Smart Aggregation Planner automatically grouped by {cat_cols[0]} for measure {measure_cols[0]}."

    # Sorting
    sorting = []
    ranking = []
    limit = None
    limit_type = "top"
    
    sort_keywords = ["sort", "order", "rank", "highest", "lowest", "top", "bottom", "most", "least"]
    if any(re.search(r"\b" + re.escape(kw) + r"\b", q_rewritten) for kw in sort_keywords):
        sort_col = None
        if aggregations:
            sort_col = aggregations[0]["column"]
        elif matched_columns:
            sort_col = matched_columns[0]
        elif known_cols:
            sort_col = known_cols[0]
            
        ascending = not any(re.search(r"\b" + re.escape(x) + r"\b", q_rewritten) for x in ["desc", "highest", "top", "most"])
        if sort_col:
            sorting.append({"column": sort_col, "ascending": ascending})

    # Limits
    limit_match = re.search(r"\b(top|bottom|highest|lowest|first|last|limit)\s+(\d+)\b", q_rewritten)
    if limit_match:
        limit_type = "bottom" if limit_match.group(1) in ("bottom", "lowest", "last") else "top"
        limit = int(limit_match.group(2))
    elif any(x in q_rewritten for x in ["highest", "lowest", "most", "least", "best", "worst"]):
        limit = 1
        limit_type = "bottom" if any(x in q_rewritten for x in ["lowest", "least", "worst"]) else "top"

    # Chart recommendation
    chart_type = None
    if has_viz:
        intent = "visualization"
        confidence = 0.95
        if "bar" in q_rewritten: chart_type = "bar"
        elif "line" in q_rewritten or "time series" in q_rewritten or "trend" in q_rewritten: chart_type = "line"
        elif "scatter" in q_rewritten or "relationship" in q_rewritten or "vs" in q_rewritten: chart_type = "scatter"
        elif "box" in q_rewritten: chart_type = "box"
        elif "histogram" in q_rewritten or "distribution" in q_rewritten: chart_type = "histogram"
        elif "pie" in q_rewritten: chart_type = "pie"
        elif "heatmap" in q_rewritten or "correlation" in q_rewritten: chart_type = "heatmap"
        elif "area" in q_rewritten: chart_type = "area"
        elif "treemap" in q_rewritten: chart_type = "treemap"

    # Final intent resolution
    if intent == "id_lookup":
        pass
    elif has_predict:
        intent = "prediction"
        confidence = 0.95
    elif has_insight:
        intent = "insight"
        confidence = 0.95
    elif has_meta:
        intent = "metadata"
        confidence = 0.95
    elif has_viz:
        pass
    elif aggregations:
        intent = "aggregation"
        confidence = 0.90
    elif filters:
        intent = "filter"
        confidence = 0.90
    elif sorting:
        intent = "sorting"
        confidence = 0.90
    elif ranking:
        intent = "ranking"
        confidence = 0.90
    elif matched_columns:
        intent = "lookup"
        confidence = 0.90

    # Ambiguity check
    # E.g. "sales by date" when multiple date columns exist, we score confidence
    # If there are multiple date columns, and no exact match, we resolve to the highest probability (e.g. Order Date)
    if active_df is not None:
        date_cols = [c for c in known_cols if "date" in c.lower()]
        if len(date_cols) >= 2 and any(w in q_rewritten for w in ["date", "time"]):
            # If no specific date column is typed, resolve order date (91% confidence vs ship date 9%)
            order_date_col = [c for c in date_cols if "order" in c.lower()]
            if order_date_col:
                matched_columns = [order_date_col[0]]
                confidence = 0.91
                match_reason = "Ambiguity resolved automatically: selected Order Date over other date columns."

    # Redirect HAVING filters targeting groupby columns to the aggregated numeric columns
    if groupby_cols and aggregations:
        agg_col = aggregations[0]["column"]
        for filt in filters:
            if filt["column"] in groupby_cols:
                val = filt["value"]
                is_val_numeric = False
                if isinstance(val, list):
                    is_val_numeric = all(isinstance(x, (int, float)) for x in val)
                else:
                    is_val_numeric = isinstance(val, (int, float))
                if is_val_numeric:
                    filt["column"] = agg_col

    # Construct baseline execution plan
    execution_plan = {
        "intent": intent,
        "filters": filters,
        "aggregations": aggregations,
        "groupby": groupby_cols,
        "sorting": sorting,
        "ranking": ranking,
        "chart_type": chart_type,
        "limit": limit,
        "limit_type": limit_type,
        "offset": 0
    }

    # Apply Multi-turn memory merging
    if prev_plan and active_df is not None:
        execution_plan = merge_conversational_context(execution_plan, prev_plan, question, active_df, conversation_id=conversation_id)
        intent = execution_plan.get("intent", intent)

    # Force fallback if filters specified but not matched
    filter_keywords = {"where", "whose", "between", "only", "greater", "less", "above", "below", "equal", ">", "<", "=", "!=", "contains", "starts", "ends", "in"}
    has_filter_words = any(w in q_rewritten for w in filter_keywords) or any(op in q_rewritten for op in [">", "<", "=", "!="])
    if has_filter_words and not execution_plan.get("filters") and intent in ("filter", "lookup"):
        intent = "fallback"
        confidence = 0.0
        
    if len(execution_plan.get("filters", [])) > 3 or len(execution_plan.get("aggregations", [])) > 2:
        confidence = 0.60 # Complex query, LLM best suited

    # Compile intermediate DSL
    dsl = compile_to_dsl(execution_plan)
    execution_plan["dsl"] = dsl
    execution_plan["plan_id"] = str(uuid.uuid4())
    execution_plan["created_at"] = datetime.datetime.now().isoformat()
    execution_plan["confidence"] = confidence
    
    # Store ID Target if id_lookup
    if intent == "id_lookup":
        execution_plan["id_column"] = id_lookup_col
        execution_plan["id_value"] = id_lookup_target

    return ParsedQuery(
        intent=intent,
        confidence=confidence,
        entities={
            "matched_columns": matched_columns,
            "matched_categorical": matched_categorical
        },
        filters=execution_plan.get("filters", []),
        aggregations=execution_plan.get("aggregations", []),
        sorting=execution_plan.get("sorting", []),
        ranking=execution_plan.get("ranking", []),
        chart_type=execution_plan.get("chart_type"),
        execution_plan=execution_plan
    )
