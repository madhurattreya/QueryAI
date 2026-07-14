import re
import pandas as pd
from dataclasses import dataclass, field
import backend.config as config

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

def get_categorical_values(df_name: str, df: pd.DataFrame, col: str) -> set:
    cache_key = (df_name, col)
    if cache_key in _categorical_values_cache:
        return _categorical_values_cache[cache_key]
    
    val_set = set()
    if df[col].dtype == 'object' or isinstance(df[col].dtype, pd.CategoricalDtype):
        try:
            if df[col].nunique() < 1000:
                val_set = {str(val).strip().lower() for val in df[col].dropna().unique() if str(val).strip()}
        except Exception:
            pass
    _categorical_values_cache[cache_key] = val_set
    return val_set

def parse_question(question: str, active_df: pd.DataFrame = None, active_df_name: str = "") -> ParsedQuery:
    """
    Parses natural language question dynamically into ParsedQuery execution plan.
    Target latency: < 5ms.
    """
    q_norm = question.strip().lower()
    
    # 1. Standardize formatting (e.g. remove commas from numbers: 60,000 -> 60000)
    while re.search(r"\b(\d+),(\d+)\b", q_norm):
        q_norm = re.sub(r"\b(\d+),(\d+)\b", r"\1\2", q_norm)
        
    # 2. Extract known schema elements & build column mappings
    cols_map = {}
    known_cols = []
    if active_df is not None:
        known_cols = active_df.columns.tolist()
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

    # Helper to resolve columns
    def resolve_column(name: str) -> str:
        name_clean = name.strip().lower()
        if name_clean in cols_map:
            return cols_map[name_clean]
        # Try fuzzy match
        for k, v in cols_map.items():
            if name_clean in k or k in name_clean:
                return v
        return None

    # 3. Intent Heuristics (initially lookup)
    intent = "lookup"
    confidence = 0.50
    
    # Check general chat
    chat_words = {"hello", "hi", "hey", "greetings", "thanks", "thank you", "who are you", "what can you do", "joke", "help", "capabilities"}
    words_in_q = set(re.findall(r"\b[a-z0-9_]+\b", q_norm))
    if words_in_q.intersection(chat_words) and not active_df_name:
        return ParsedQuery(intent="general_chat", confidence=0.95)
        
    # Detect viz/predict/insight/metadata keywords
    viz_keywords = {"chart", "graph", "plot", "pie", "bar", "line", "histogram", "scatter", "box", "heatmap", "area", "treemap", "dashboard"}
    has_viz = any(kw in q_norm for kw in viz_keywords)
    
    predict_keywords = {"predict", "forecast", "extrapolate", "growth", "prediction"}
    has_predict = any(kw in q_norm for kw in predict_keywords)
    
    insight_keywords = {"insight", "hidden", "analysis", "trend", "pattern", "business", "key finding", "observation", "summary"}
    has_insight = any(kw in q_norm for kw in insight_keywords)
    
    meta_keywords = {"how many tables", "show tables", "columns of", "describe table", "list tables", "schema", "dataset info"}
    has_meta = any(kw in q_norm for kw in meta_keywords)

    # Match columns mentioned in question
    matched_columns = []
    for col_lower, col_orig in cols_map.items():
        # Match with boundary check (accounting for underscore substitution)
        if re.search(r'\b' + re.escape(col_lower) + r'\b', q_norm) or re.search(r'\b' + re.escape(col_lower.replace(" ", "_")) + r'\b', q_norm):
            if col_orig not in matched_columns:
                matched_columns.append(col_orig)

    # 4. Complex Multi-Filter Extraction
    filters = []
    
    # We will scan for filter patterns sequentially. To prevent double-matching,
    # as we match each filter pattern, we replace the matched string with a unique placeholder.
    filter_placeholders = [] # List of tuples: (start_index, placeholder_name, filter_dict)
    
    # Pattern 1: Null Check
    # "Salary is null", "experience is not null"
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
            
    # Pattern 2: Range Filter
    # "Salary is between 60000 and 80000"
    range_pattern = r"\b([a-z_0-9]+)\s+(?:is\s+)?(between|not\s+between)\s+['\"]?([a-z0-9_\-\.\/]+)['\"]?\s+and\s+['\"]?([a-z0-9_\-\.\/]+)['\"]?\b"
    for match in re.finditer(range_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op_text = match.group(2)
            op = "not between" if "not" in op_text else "between"
            val1, val2 = match.group(3), match.group(4)
            try:
                val1, val2 = float(val1), float(val2)
            except ValueError:
                pass
            filt = {"column": col_name, "operator": op, "value": [val1, val2]}
            placeholder = f"__FP_RANGE_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Pattern 3: List Filter
    # "Department is in ['IT', 'HR']", "Salary not in (50000, 60000)"
    list_pattern = r"\b([a-z_0-9]+)\s+(?:is\s+)?(in|not\s+in)\s*[\(\[]\s*([a-z0-9_\s'\",]+)\s*[\)\]]"
    for match in re.finditer(list_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op = match.group(2)
            raw_vals = match.group(3)
            vals = [v.strip().strip("'\"") for v in raw_vals.split(",") if v.strip()]
            parsed_vals = []
            for v in vals:
                try:
                    parsed_vals.append(float(v) if '.' in v else int(v))
                except ValueError:
                    parsed_vals.append(v)
            filt = {"column": col_name, "operator": op, "value": parsed_vals}
            placeholder = f"__FP_LIST_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Pattern 4: String Operator Filter
    # "Name contains 'John'", "Name starts with 'A'"
    string_pattern = r"\b([a-z_0-9]+)\s+(contains|like|starts\s+with|startswith|ends\s+with|endswith)\s+['\"]?([a-z0-9_\-\s]+?)['\"]?(?=\s+(?:and|or|but|not|is|between|in)\b|$)"
    for match in re.finditer(string_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op_text = match.group(2)
            op = "startswith" if "start" in op_text else "endswith" if "end" in op_text else "contains"
            val = match.group(3).strip()
            filt = {"column": col_name, "operator": op, "value": val}
            placeholder = f"__FP_STR_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Pattern 5: Numeric text comparison
    # "Salary greater than 50000", "Age equal to 30"
    text_comp_pattern = r"\b([a-z_0-9]+)\s+(?:is\s+|are\s+|was\s+)?(greater\s+than|less\s+than|above|below|equal\s+to|more\s+than)\s+['\"]?([a-z0-9_\-\.\/]+?)['\"]?(?=\s+(?:and|or|but|not|is|between|in)\b|$)"
    for match in re.finditer(text_comp_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op_cand = match.group(2)
            val_cand = match.group(3)
            try:
                val_cand = float(val_cand)
            except ValueError:
                pass
            op_map = {
                "greater than": ">", "above": ">", "more than": ">",
                "less than": "<", "below": "<", "equal to": "=="
            }
            filt = {"column": col_name, "operator": op_map.get(op_cand, "=="), "value": val_cand}
            placeholder = f"__FP_TXT_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Pattern 6: Standard symbolic comparison
    # "Salary > 50000", "experience != 5"
    comp_pattern = r"\b([a-z_0-9]+)\s*(?:is\s+|are\s+|was\s+)?(>=|<=|>|<|!=|==|=)\s*['\"]?([a-z0-9_\-\.\/]+?)['\"]?(?=\s+(?:and|or|but|not|is|between|in)\b|$)"
    for match in re.finditer(comp_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            op_cand = match.group(2)
            val_cand = match.group(3)
            try:
                val_cand = float(val_cand)
            except ValueError:
                pass
            op_map = {"=": "==", "==": "==", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<="}
            filt = {"column": col_name, "operator": op_map.get(op_cand, "=="), "value": val_cand}
            placeholder = f"__FP_SYM_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Pattern 7: "is" comparison
    # "Department is IT", "Name is Amit"
    is_pattern = r"\b([a-z_0-9]+)\s+(?:is|equal)\s+['\"]?([a-z0-9_\-\s\.\/]+?)['\"]?(?=\s+(?:and|or|but|not|is|between|in)\b|$)"
    for match in re.finditer(is_pattern, q_norm):
        col_name = resolve_column(match.group(1))
        if col_name:
            val_cand = match.group(2).strip()
            try:
                val_cand = float(val_cand)
            except ValueError:
                pass
            filt = {"column": col_name, "operator": "==", "value": val_cand}
            placeholder = f"__FP_IS_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Pattern 8: Date/Year extraction
    # "joined before 2020", "joined after 2018"
    date_matches = re.finditer(r"\b(before|after|in|since|until)\s+(\d{4})\b", q_norm)
    for match in date_matches:
        op_cand = match.group(1)
        year_cand = int(match.group(2))
        
        date_cols = [c for c in matched_columns if "date" in c.lower() or "joined" in c.lower() or "hired" in c.lower()]
        if not date_cols and active_df is not None:
            date_cols = [c for c in known_cols if "date" in c.lower() or "joined" in c.lower() or "hired" in c.lower()]
            
        if date_cols:
            col = date_cols[0]
            if op_cand == "before":
                filt = {"column": col, "operator": "<", "value": f"{year_cand}-01-01"}
            elif op_cand in ("after", "since"):
                filt = {"column": col, "operator": ">", "value": f"{year_cand}-12-31"}
            elif op_cand == "in":
                filt = {"column": col, "operator": "between", "value": [f"{year_cand}-01-01", f"{year_cand}-12-31"]}
            else:
                filt = {"column": col, "operator": "<=", "value": f"{year_cand}-12-31"}
                
            placeholder = f"__FP_DATE_{len(filter_placeholders)}__"
            filter_placeholders.append((match.start(), placeholder, filt))
            q_norm = q_norm[:match.start()] + placeholder.ljust(match.end() - match.start()) + q_norm[match.end():]

    # Sort placeholders by index to process them left-to-right
    filter_placeholders.sort(key=lambda x: x[0])
    
    # Extract logical relations
    filters = []
    for idx, (_, placeholder, filt) in enumerate(filter_placeholders):
        logical_relation = "and"
        if idx > 0:
            # Check text between end of previous match and start of current match
            prev_end = filter_placeholders[idx-1][0]
            curr_start = filter_placeholders[idx][0]
            between_text = q_norm[prev_end:curr_start].lower()
            if "or" in re.findall(r"\b(or|but)\b", between_text):
                logical_relation = "or"
        
        filt_copy = filt.copy()
        filt_copy["logical_relation"] = logical_relation
        filters.append(filt_copy)

    # 6. Categorical implicit matches extraction (for any columns NOT explicitly filtered yet)
    matched_categorical = {}
    explicit_filtered_cols = {f["column"].lower() for f in filters}
    
    if active_df is not None and active_df_name:
        for col in known_cols:
            if col.lower() in explicit_filtered_cols:
                continue
            vals = get_categorical_values(active_df_name, active_df, col)
            if vals:
                for val in vals:
                    # Look for value as a distinct word in the question
                    if re.search(r'\b' + re.escape(val) + r'\b', q_clean):
                        matched_categorical[col] = val
                        
    for col, val in matched_categorical.items():
        orig_val = val
        if active_df is not None:
            matches = active_df[active_df[col].astype(str).str.lower() == val]
            if not matches.empty:
                orig_val = matches[col].iloc[0]
        # Append implicit categorical matches as "and" filters
        filters.append({"column": col, "operator": "==", "value": orig_val, "logical_relation": "and"})

    # 7. Aggregation Detection
    aggregations = []
    agg_keywords = {
        "average": "mean", "mean": "mean", "avg": "mean", "sum": "sum", "total": "sum",
        "count": "count", "max": "max", "min": "min", "highest": "max",
        "lowest": "min", "median": "median", "std": "std", "variance": "var",
        "percentile": "quantile"
    }
    for kw, op in agg_keywords.items():
        if re.search(r'\b' + re.escape(kw) + r'\b', q_clean):
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
                
    # 8. Group By Detection
    groupby_cols = []
    if "by" in q_clean or "wise" in q_clean:
        for col in known_cols:
            col_l = col.lower()
            if f"by {col_l}" in q_clean or f"{col_l}-wise" in q_clean or f"{col_l} wise" in q_clean:
                groupby_cols.append(col)
                
    # 9. Sorting & Top N / Bottom N limits
    sorting = []
    ranking = []
    limit = None
    limit_type = "top"
    
    # Sort/Rank check
    if "sort" in q_clean or "order" in q_clean or "rank" in q_clean or "highest" in q_clean or "lowest" in q_clean or "top" in q_clean or "bottom" in q_clean:
        sort_col = matched_columns[0] if matched_columns else (known_cols[0] if known_cols else None)
        ascending = "desc" not in q_clean and "highest" not in q_clean and "top" not in q_clean
        if sort_col:
            sorting.append({"column": sort_col, "ascending": ascending})
            
    if "rank" in q_clean:
        rank_col = matched_columns[0] if matched_columns else (known_cols[0] if known_cols else None)
        if rank_col:
            ranking.append({"column": rank_col, "method": "dense" if "dense" in q_clean else "average"})

    # Limit (top/bottom N) check
    limit_match = re.search(r"\b(top|bottom|highest|lowest|first|last|limit)\s+(\d+)\b", q_clean)
    if limit_match:
        limit_type = "bottom" if limit_match.group(1) in ("bottom", "lowest", "last") else "top"
        limit = int(limit_match.group(2))

    # 10. Chart recommendation
    chart_type = None
    if has_viz:
        intent = "visualization"
        confidence = 0.95
        if "bar" in q_clean:
            chart_type = "bar"
        elif "line" in q_clean or "time series" in q_clean or "trend" in q_clean:
            chart_type = "line"
        elif "scatter" in q_clean or "relationship" in q_clean or "vs" in q_clean:
            chart_type = "scatter"
        elif "box" in q_clean:
            chart_type = "box"
        elif "histogram" in q_clean or "distribution" in q_clean:
            chart_type = "histogram"
        elif "pie" in q_clean:
            chart_type = "pie"
        elif "heatmap" in q_clean or "correlation" in q_clean:
            chart_type = "heatmap"
        elif "area" in q_clean:
            chart_type = "area"
        elif "treemap" in q_clean:
            chart_type = "treemap"

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

    # 11. Final Intent & Confidence resolution
    if has_predict:
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

    # Rule 6 Compliance:
    # If the question contains filtering words, but the parser extracted NO filters,
    # then the parser failed to parse the filter. Set confidence to 0.0 to force fallback!
    filter_keywords = {"where", "whose", "between", "only", "greater", "less", "above", "below", "equal", ">", "<", "=", "contains", "starts", "ends", "in"}
    has_filter_words = any(w in q_clean for w in filter_keywords) or any(op in q_clean for op in [">", "<", "=", "!="])
    if has_filter_words and not filters and intent in ("filter", "lookup"):
        intent = "fallback"
        confidence = 0.0
        
    # Build execution plan
    execution_plan = {
        "intent": intent,
        "filters": filters,
        "aggregations": aggregations,
        "groupby": groupby_cols,
        "sorting": sorting,
        "ranking": ranking,
        "chart_type": chart_type,
        "limit": limit,
        "limit_type": limit_type
    }
    
    if len(filters) > 3 or len(aggregations) > 2 or (len(filters) > 0 and len(aggregations) > 0 and groupby_cols):
        # Mark extremely complex queries for LLM
        confidence = 0.60
        
    return ParsedQuery(
        intent=intent,
        confidence=confidence,
        entities={
            "matched_columns": matched_columns,
            "matched_categorical": matched_categorical
        },
        filters=filters,
        aggregations=aggregations,
        sorting=sorting,
        ranking=ranking,
        chart_type=chart_type,
        execution_plan=execution_plan
    )
