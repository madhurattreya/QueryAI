import pandas as pd
import numpy as np
import difflib
import backend.config as config
from backend.services.query_parser import ParsedQuery

def evaluate_filter_condition(df: pd.DataFrame, col: str, op: str, val: any) -> pd.Series:
    """
    Evaluates a single filter condition on a DataFrame column with safe type conversions and fuzzy corrections.
    """
    if col not in df.columns:
        return pd.Series(False, index=df.index)
        
    series = df[col]
    
    # 1. Date/Time Conversion Heuristics
    is_date_col = (
        pd.api.types.is_datetime64_any_dtype(series) or
        "date" in col.lower() or "joined" in col.lower() or "hired" in col.lower()
    )
    if is_date_col:
        try:
            series = pd.to_datetime(series, errors="coerce")
            if isinstance(val, list):
                val = [pd.to_datetime(v, errors="coerce") for v in val]
            elif val is not None:
                val = pd.to_datetime(val, errors="coerce")
        except Exception:
            pass

    # 2. Numeric Conversion Heuristics
    is_num_col = pd.api.types.is_numeric_dtype(series)
    if is_num_col and not is_date_col:
        try:
            if isinstance(val, list):
                val = [float(v) if v is not None else None for v in val]
            elif val is not None:
                val = float(val)
        except Exception:
            pass

    # 3. Categorical & Fuzzy Matching
    is_str_col = pd.api.types.is_string_dtype(series) or isinstance(series.dtype, pd.CategoricalDtype)
    if is_str_col and val is not None and not isinstance(val, list):
        try:
            unique_vals = [str(x) for x in series.dropna().unique()]
            val_str = str(val).strip().lower()
            
            # Exact case-insensitive match first
            exact_match = None
            for uv in unique_vals:
                if uv.strip().lower() == val_str:
                    exact_match = uv
                    break
            
            if exact_match:
                val = exact_match
            else:
                matches = difflib.get_close_matches(str(val), unique_vals, n=1, cutoff=0.7)
                if matches:
                    val = matches[0]
        except Exception:
            pass

    # 4. Operator Evaluation
    if op == "==":
        if is_str_col:
            return series.astype(str).str.strip().str.lower() == str(val).strip().lower()
        return series == val
    elif op == "!=":
        if is_str_col:
            return series.astype(str).str.strip().str.lower() != str(val).strip().lower()
        return series != val
    elif op == ">": return series > val
    elif op == ">=": return series >= val
    elif op == "<": return series < val
    elif op == "<=": return series <= val
    elif op == "between":
        if isinstance(val, list) and len(val) == 2:
            return series.between(val[0], val[1])
        raise ValueError(f"Invalid range values for between operator: {val}")
    elif op == "not between":
        if isinstance(val, list) and len(val) == 2:
            return ~series.between(val[0], val[1])
        raise ValueError(f"Invalid range values for not between operator: {val}")
    elif op in ("contains", "like"):
        return series.astype(str).str.contains(str(val), case=False, na=False)
    elif op in ("startswith", "starts with"):
        return series.astype(str).str.lower().str.startswith(str(val).lower(), na=False)
    elif op in ("endswith", "ends with"):
        return series.astype(str).str.lower().str.endswith(str(val).lower(), na=False)
    elif op == "in":
        if isinstance(val, list):
            if is_str_col:
                val_set = {str(v).strip().lower() for v in val}
                return series.astype(str).str.strip().str.lower().isin(val_set)
            return series.isin(val)
        raise ValueError(f"Operator 'in' requires a list, got: {type(val)}")
    elif op == "not in":
        if isinstance(val, list):
            if is_str_col:
                val_set = {str(v).strip().lower() for v in val}
                return ~series.astype(str).str.strip().str.lower().isin(val_set)
            return ~series.isin(val)
        raise ValueError(f"Operator 'not in' requires a list, got: {type(val)}")
    elif op in ("is_null", "is null", "null"):
        return series.isna()
    elif op in ("is_not_null", "is not null", "not null"):
        return ~series.isna()
        
    raise ValueError(f"Unsupported filter operator: {op}")

def get_filter_expr_str(df_name: str, col: str, op: str, val: any) -> str:
    val_str = f"'{val}'" if isinstance(val, str) else str(val)
    if op == "==": return f"({df_name}['{col}'] == {val_str})"
    elif op == "!=": return f"({df_name}['{col}'] != {val_str})"
    elif op in (">", ">=", "<", "<="): return f"({df_name}['{col}'] {op} {val_str})"
    elif op == "between": return f"({df_name}['{col}'].between({val[0]}, {val[1]}))"
    elif op == "not between": return f"(~{df_name}['{col}'].between({val[0]}, {val[1]}))"
    elif op in ("contains", "like"): return f"({df_name}['{col}'].astype(str).str.contains('{val}', case=False, na=False))"
    elif op in ("startswith", "starts with"): return f"({df_name}['{col}'].astype(str).str.startswith('{val}', na=False))"
    elif op in ("endswith", "ends with"): return f"({df_name}['{col}'].astype(str).str.endswith('{val}', na=False))"
    elif op == "in": return f"({df_name}['{col}'].isin({val}))"
    elif op == "not in": return f"(~{df_name}['{col}'].isin({val}))"
    elif op in ("is_null", "is null", "null"): return f"({df_name}['{col}'].isna())"
    elif op in ("is_not_null", "is not null", "not null"): return f"(~{df_name}['{col}'].isna())"
    return f"({df_name}['{col}'] {op} {val_str})"

def execute_analytics_lib(parsed: ParsedQuery, df: pd.DataFrame, df_name: str = "df") -> tuple:
    """
    Checks for and executes Analytics Library operations locally.
    """
    import backend.services.analytics_lib as al
    q_lower = parsed.execution_plan.get("question", "").lower()
    
    measure_col = parsed.aggregations[0]["column"] if parsed.aggregations else (parsed.entities.get("matched_columns")[0] if parsed.entities.get("matched_columns") else None)
    cat_col = parsed.execution_plan.get("groupby")[0] if parsed.execution_plan.get("groupby") else None
    
    date_cols = [col for col in df.columns if "date" in col.lower() or "joined" in col.lower() or "hired" in col.lower()]
    date_col = date_cols[0] if date_cols else None
    
    if not measure_col:
        active_numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        if active_numeric_cols:
            measure_col = active_numeric_cols[0]
        
    if not cat_col:
        active_cat_cols = [c for c in df.columns if df[c].dtype == 'object' or isinstance(df[c].dtype, pd.CategoricalDtype)]
        if active_cat_cols:
            cat_col = active_cat_cols[0]

    if "cagr" in q_lower and measure_col and date_col:
        df_sorted = df.sort_values(by=date_col)
        start_val = float(df_sorted[measure_col].iloc[0])
        end_val = float(df_sorted[measure_col].iloc[-1])
        years = (df_sorted[date_col].max() - df_sorted[date_col].min()).days / 365.25
        if years > 0:
            val = al.calculate_cagr(start_val, end_val, years)
            return pd.DataFrame([{"CAGR": f"{val * 100:.2f}%"}]), f"calculate_cagr({start_val}, {end_val}, {years})"
            
    elif ("yoy" in q_lower or "mom" in q_lower or "qoq" in q_lower) and measure_col and date_col:
        period = "YoY" if "yoy" in q_lower else "QoQ" if "qoq" in q_lower else "MoM"
        res = al.calculate_growth_rate(df, date_col, measure_col, period)
        return res, f"calculate_growth_rate({df_name}, '{date_col}', '{measure_col}', '{period}')"
        
    elif ("pareto" in q_lower or "80/20" in q_lower or "80-20" in q_lower) and measure_col and cat_col:
        res = al.calculate_pareto(df, cat_col, measure_col)
        return res, f"calculate_pareto({df_name}, '{cat_col}', '{measure_col}')"
        
    elif "abc" in q_lower and measure_col and cat_col:
        res = al.calculate_abc_classification(df, cat_col, measure_col)
        return res, f"calculate_abc_classification({df_name}, '{cat_col}', '{measure_col}')"
        
    elif ("anomaly" in q_lower or "outlier" in q_lower) and measure_col:
        is_anomaly = al.detect_anomalies(df, measure_col)
        res = df[is_anomaly]
        return res, f"{df_name}[detect_anomalies({df_name}, '{measure_col}')]"
        
    elif "forecast" in q_lower and measure_col and date_col:
        res = al.simple_forecast(df, date_col, measure_col)
        return res, f"simple_forecast({df_name}, '{date_col}', '{measure_col}')"
        
    elif ("moving average" in q_lower or "rolling" in q_lower) and measure_col:
        ma = al.calculate_moving_average(df, measure_col)
        res = df.copy()
        res["Moving_Average"] = ma
        return res, f"calculate_moving_average({df_name}, '{measure_col}')"
        
    elif ("running total" in q_lower or "cumulative" in q_lower) and measure_col:
        rt = al.calculate_running_total(df, measure_col)
        res = df.copy()
        res["Running_Total"] = rt
        return res, f"calculate_running_total({df_name}, '{measure_col}')"
        
    return None, None

def execute_parsed_query(parsed: ParsedQuery, df: pd.DataFrame, df_name: str = "df") -> tuple:
    """
    Executes the ParsedQuery plan deterministically against the active DataFrame using vectorized Pandas operations.
    Returns: (result_object, pandas_expression_str)
    """
    if df is None or df.empty:
        return df, f"{df_name}.copy()"

    # Intercept and append any calculated columns
    from backend.services.semantic_model import SemanticModelManager
    from backend.services.formula_engine import FormulaEngine
    import backend.services.history_db as db
    
    # Try finding the dataset ID in SQLite
    dataset_id = None
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM datasets WHERE name = ? LIMIT 1", (df_name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            dataset_id = row["id"]
    except Exception:
        pass
        
    formula_eng = FormulaEngine()
    if dataset_id:
        try:
            semantic_manager = SemanticModelManager()
            semantic_items = semantic_manager.get_model_items(dataset_id)
            for item in semantic_items:
                if item["type"] == "calculated_column":
                    col_name = item["name"]
                    if col_name not in df.columns:
                        df[col_name] = formula_eng.evaluate_calculated_column(df, item["expression"])
        except Exception as e:
            print(f"[FORMULA ENGINE WARNING] Calculated columns load failed: {e}")

    # 1. Check ID Lookup intent
    if parsed.intent == "id_lookup":
        id_col = parsed.execution_plan.get("id_column")
        id_val = parsed.execution_plan.get("id_value")
        if id_col and id_val:
            mask = df[id_col].astype(str).str.strip().str.lower() == str(id_val).strip().lower()
            res = df[mask]
            return res, f"{df_name}[{df_name}['{id_col}'].astype(str).str.strip().str.lower() == '{str(id_val).strip().lower()}']"

    # 2. Check for Analytics Library execution path
    q_lower = parsed.execution_plan.get("question", "").lower()
    if parsed.intent == "analytics_lib" or any(kw in q_lower for kw in ["cagr", "yoy", "mom", "qoq", "pareto", "abc", "anomaly", "forecast", "moving average", "running total"]):
        res_df, code_expr = execute_analytics_lib(parsed, df, df_name)
        if res_df is not None:
            return res_df, code_expr

    expr_parts = []
    groupby_cols = parsed.execution_plan.get("groupby", [])
    where_filters = []
    having_filters = []
    
    if groupby_cols and parsed.aggregations:
        agg_col = parsed.aggregations[0]["column"]
        for filt in parsed.filters:
            if filt["column"] == agg_col:
                having_filters.append(filt)
            else:
                where_filters.append(filt)
    else:
        where_filters = parsed.filters

    # 3. Evaluate pre-aggregation (WHERE) filters
    if where_filters:
        mask = None
        filter_exprs = []
        for filt in where_filters:
            col = filt["column"]
            op = filt["operator"]
            val = filt["value"]
            conn = filt.get("logical_relation", "and").lower()
            
            cond = evaluate_filter_condition(df, col, op, val)
            filter_expr = get_filter_expr_str(df_name, col, op, val)
            
            if mask is None:
                mask = cond
                filter_exprs.append(filter_expr)
            else:
                if conn == "or":
                    mask |= cond
                    filter_exprs.append(f" | {filter_expr}")
                else:
                    mask &= cond
                    filter_exprs.append(f" & {filter_expr}")
                    
        active_df = df[mask]
        expr_parts.append(f"{df_name}[{''.join(filter_exprs)}]")
    else:
        active_df = df.copy()

    # 4. Apply Group By Aggregations
    if groupby_cols:
        groupby_expr = f".groupby({groupby_cols})"
        base_df_ref = expr_parts[-1] if expr_parts else df_name
        
        if parsed.aggregations:
            agg_col = parsed.aggregations[0]["column"]
            agg_op = parsed.aggregations[0]["operator"]
            
            # Check if this is a custom calculated measure
            if dataset_id:
                try:
                    semantic_manager = SemanticModelManager()
                    measure_item = semantic_manager.get_model_item_by_name(agg_col, dataset_id)
                    if measure_item and measure_item["type"] in ("calculated_measure", "measure"):
                        expr = measure_item["expression"]
                        referenced_cols = [c for c in active_df.columns if c in expr]
                        agg_dict = {c: "sum" for c in referenced_cols if pd.api.types.is_numeric_dtype(active_df[c])}
                        grouped_res = active_df.groupby(groupby_cols).agg(agg_dict).reset_index()
                        
                        # Evaluate calculated measure expression on grouped results
                        py_expr = formula_eng.parse_and_translate_expression(expr, "grouped_res")
                        local_vars = {"grouped_res": grouped_res, "np": np}
                        grouped_res[agg_col] = eval(py_expr, {"__builtins__": {}}, local_vars)
                        
                        res = grouped_res[groupby_cols + [agg_col]]
                        code_expr = f"{base_df_ref}.groupby({groupby_cols}).agg({agg_dict}).reset_index()\nresult['{agg_col}'] = FormulaEngine().evaluate_calculated_column(result, '{expr}')"
                        active_df = res
                        expr_parts.append(code_expr)
                        # Skip standard agg processing
                        agg_op = None 
                except Exception as e:
                    print(f"[FORMULA ENGINE WARNING] Grouped calculated measure failed: {e}")

            if agg_op == "mean":
                res = active_df.groupby(groupby_cols)[agg_col].mean().reset_index()
                op_str = ".mean()"
            elif agg_op == "sum":
                res = active_df.groupby(groupby_cols)[agg_col].sum().reset_index()
                op_str = ".sum()"
            elif agg_op == "count":
                res = active_df.groupby(groupby_cols)[agg_col].count().reset_index()
                op_str = ".count()"
            elif agg_op == "max":
                res = active_df.groupby(groupby_cols)[agg_col].max().reset_index()
                op_str = ".max()"
            elif agg_op == "min":
                res = active_df.groupby(groupby_cols)[agg_col].min().reset_index()
                op_str = ".min()"
            elif agg_op == "median":
                res = active_df.groupby(groupby_cols)[agg_col].median().reset_index()
                op_str = ".median()"
            else:
                res = active_df.groupby(groupby_cols)[agg_col].mean().reset_index()
                op_str = ".mean()"
                
            code_expr = f"{base_df_ref}{groupby_expr}['{agg_col}']{op_str}.reset_index()"
            active_df = res
            expr_parts.append(code_expr)
        else:
            res = active_df.groupby(groupby_cols).size().reset_index(name="count")
            code_expr = f"{base_df_ref}{groupby_expr}.size().reset_index(name='count')"
            active_df = res
            expr_parts.append(code_expr)

        # Apply HAVING filters
        if having_filters:
            h_mask = None
            h_exprs = []
            base_df_ref = expr_parts[-1]
            for filt in having_filters:
                col = filt["column"]
                op = filt["operator"]
                val = filt["value"]
                conn = filt.get("logical_relation", "and").lower()
                
                cond = evaluate_filter_condition(active_df, col, op, val)
                filter_expr = get_filter_expr_str("res", col, op, val)
                
                if h_mask is None:
                    h_mask = cond
                    h_exprs.append(filter_expr)
                else:
                    if conn == "or":
                        h_mask |= cond
                        h_exprs.append(f" | {filter_expr}")
                    else:
                        h_mask &= cond
                        h_exprs.append(f" & {filter_expr}")
                        
            active_df = active_df[h_mask]
            expr_parts.append(f"({base_df_ref})[{''.join(h_exprs)}]")

    # 5. Simple Aggregations (Single Metrics)
    elif parsed.aggregations and not groupby_cols:
        agg = parsed.aggregations[0]
        col = agg["column"]
        op = agg["operator"]
        base_df_ref = expr_parts[-1] if expr_parts else df_name
        
        # Check if the column name represents a calculated measure
        if dataset_id:
            try:
                semantic_manager = SemanticModelManager()
                measure_item = semantic_manager.get_model_item_by_name(col, dataset_id)
                if measure_item and measure_item["type"] in ("calculated_measure", "measure"):
                    val = formula_eng.evaluate_calculated_measure(active_df, measure_item["expression"])
                    return val, f"FormulaEngine().evaluate_calculated_measure({base_df_ref}, '{measure_item['expression']}')"
            except Exception as e:
                print(f"[FORMULA ENGINE WARNING] Calculated measure evaluation failed: {e}")
        
        if op == "mean":
            val = active_df[col].mean()
            code_expr = f"{base_df_ref}['{col}'].mean()"
        elif op == "sum":
            val = active_df[col].sum()
            code_expr = f"{base_df_ref}['{col}'].sum()"
        elif op == "count":
            val = len(active_df)
            code_expr = f"len({base_df_ref})"
        elif op == "max":
            if not active_df.empty:
                idx = active_df[col].idxmax()
                val = active_df.loc[[idx]]
                code_expr = f"{base_df_ref}.loc[[{base_df_ref}['{col}'].idxmax()]]"
            else:
                val = active_df
                code_expr = f"{base_df_ref}"
        elif op == "min":
            if not active_df.empty:
                idx = active_df[col].idxmin()
                val = active_df.loc[[idx]]
                code_expr = f"{base_df_ref}.loc[[{base_df_ref}['{col}'].idxmin()]]"
            else:
                val = active_df
                code_expr = f"{base_df_ref}"
        elif op == "median":
            val = active_df[col].median()
            code_expr = f"{base_df_ref}['{col}'].median()"
        elif op == "std":
            val = active_df[col].std()
            code_expr = f"{base_df_ref}['{col}'].std()"
        elif op == "var":
            val = active_df[col].var()
            code_expr = f"{base_df_ref}['{col}'].var()"
        else:
            val = len(active_df)
            code_expr = f"len({base_df_ref})"
            
        return val, code_expr

    # 6. Sorting
    if parsed.sorting:
        sort_info = parsed.sorting[0]
        col = sort_info["column"]
        asc = sort_info["ascending"]
        base_df_ref = expr_parts[-1] if expr_parts else df_name
        
        active_df = active_df.sort_values(by=col, ascending=asc)
        expr_parts.append(f"{base_df_ref}.sort_values(by='{col}', ascending={asc})")
            
    # 7. Limits & Offsets
    limit = parsed.execution_plan.get("limit")
    offset = parsed.execution_plan.get("offset", 0)
    if limit is not None or offset > 0:
        base_df_ref = expr_parts[-1] if expr_parts else df_name
        start = offset
        end = (offset + limit) if limit is not None else len(active_df)
        active_df = active_df.iloc[start:end]
        expr_parts.append(f"{base_df_ref}.iloc[{start}:{end}]")

    final_expr = expr_parts[-1] if expr_parts else f"{df_name}.copy()"
    return active_df, final_expr
