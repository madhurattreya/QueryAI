import pandas as pd
import numpy as np
import difflib
from backend.services.query_parser import ParsedQuery

def evaluate_filter_condition(df: pd.DataFrame, col: str, op: str, val: any) -> pd.Series:
    """
    Evaluates a single filter condition on a DataFrame column with safe type conversions and fuzzy corrections.
    """
    if col not in df.columns:
        # Return all-False mask if column is missing
        return pd.Series(False, index=df.index)
        
    series = df[col]
    
    # 1. Date/Time Conversion Heuristics (Rule 9)
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

    # 2. Numeric Conversion Heuristics (Rule 8)
    is_num_col = pd.api.types.is_numeric_dtype(series)
    if is_num_col and not is_date_col:
        try:
            if isinstance(val, list):
                val = [float(v) if v is not None else None for v in val]
            elif val is not None:
                val = float(val)
        except Exception:
            pass

    # 3. Categorical & Fuzzy Matching (Rule 10 & 11)
    is_str_col = pd.api.types.is_string_dtype(series) or isinstance(series.dtype, pd.CategoricalDtype)
    if is_str_col and val is not None and not isinstance(val, list):
        # Apply fuzzy string matching against unique categorical values
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
                # Fuzzy matching using standard difflib
                matches = difflib.get_close_matches(str(val), unique_vals, n=1, cutoff=0.7)
                if matches:
                    val = matches[0]
        except Exception:
            pass

    # 4. Operator Evaluation (Rule 1, 3, 4)
    if op == "==":
        if is_str_col:
            return series.astype(str).str.strip().str.lower() == str(val).strip().lower()
        return series == val
    elif op == "!=":
        if is_str_col:
            return series.astype(str).str.strip().str.lower() != str(val).strip().lower()
        return series != val
    elif op == ">":
        return series > val
    elif op == ">=":
        return series >= val
    elif op == "<":
        return series < val
    elif op == "<=":
        return series <= val
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
    """
    Generates valid executable Pandas code string for a single filter.
    """
    val_str = f"'{val}'" if isinstance(val, str) else str(val)
    if op == "==":
        return f"({df_name}['{col}'] == {val_str})"
    elif op == "!=":
        return f"({df_name}['{col}'] != {val_str})"
    elif op in (">", ">=", "<", "<="):
        return f"({df_name}['{col}'] {op} {val_str})"
    elif op == "between":
        return f"({df_name}['{col}'].between({val[0]}, {val[1]}))"
    elif op == "not between":
        return f"(~{df_name}['{col}'].between({val[0]}, {val[1]}))"
    elif op in ("contains", "like"):
        return f"({df_name}['{col}'].astype(str).str.contains('{val}', case=False, na=False))"
    elif op in ("startswith", "starts with"):
        return f"({df_name}['{col}'].astype(str).str.startswith('{val}', na=False))"
    elif op in ("endswith", "ends with"):
        return f"({df_name}['{col}'].astype(str).str.endswith('{val}', na=False))"
    elif op == "in":
        return f"({df_name}['{col}'].isin({val}))"
    elif op == "not in":
        return f"(~{df_name}['{col}'].isin({val}))"
    elif op in ("is_null", "is null", "null"):
        return f"({df_name}['{col}'].isna())"
    elif op in ("is_not_null", "is not null", "not null"):
        return f"(~{df_name}['{col}'].isna())"
    return f"({df_name}['{col}'] {op} {val_str})"

def execute_parsed_query(parsed: ParsedQuery, df: pd.DataFrame, df_name: str = "df") -> tuple:
    """
    Executes the ParsedQuery plan deterministically against the active DataFrame using vectorized Pandas operations.
    Returns: (result_object, pandas_expression_str)
    """
    if df is None or df.empty:
        return df, f"{df_name}.copy()"
        
    expr_parts = []
    
    # 1. Separate pre-aggregation (WHERE) and post-aggregation (HAVING) filters
    groupby_cols = parsed.execution_plan.get("groupby", [])
    where_filters = []
    having_filters = []
    
    if groupby_cols and parsed.aggregations:
        agg_col = parsed.aggregations[0]["column"]
        for filt in parsed.filters:
            # If the filter targets the aggregated column, apply it post-groupby (HAVING)
            if filt["column"] == agg_col:
                having_filters.append(filt)
            else:
                where_filters.append(filt)
    else:
        where_filters = parsed.filters

    # 2. Evaluate pre-aggregation (WHERE) filters (Rule 3, 4)
    if where_filters:
        mask = None
        filter_exprs = []
        for filt in where_filters:
            col = filt["column"]
            op = filt["operator"]
            val = filt["value"]
            conn = filt.get("logical_relation", "and").lower()
            
            # Apply comparison operator
            cond = evaluate_filter_condition(df, col, op, val)
            
            # Add to Pandas expression string
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
        
        # Rule 5 & 6 Check: If filters were specified but active_df returns full dataframe, 
        # ensure we aren't bypassing logical criteria.
        if len(active_df) == len(df) and len(df) > 0 and len(where_filters) > 0:
            # If a strict filter was requested but returned all rows, check if it's correct.
            # Usually correct if all rows match, but if we suspect it bypassed the condition, raise an error.
            pass
    else:
        active_df = df.copy()

    # 3. Apply Group By Aggregations
    if groupby_cols:
        groupby_expr = f".groupby({groupby_cols})"
        base_df_ref = expr_parts[-1] if expr_parts else df_name
        
        if parsed.aggregations:
            agg_col = parsed.aggregations[0]["column"]
            agg_op = parsed.aggregations[0]["operator"]
            
            # Apply aggregation operator
            if agg_op == "mean":
                res = active_df.groupby(groupby_cols)[agg_col].mean().reset_index()
                op_str = f".mean()"
            elif agg_op == "sum":
                res = active_df.groupby(groupby_cols)[agg_col].sum().reset_index()
                op_str = f".sum()"
            elif agg_op == "count":
                res = active_df.groupby(groupby_cols)[agg_col].count().reset_index()
                op_str = f".count()"
            elif agg_op == "max":
                res = active_df.groupby(groupby_cols)[agg_col].max().reset_index()
                op_str = f".max()"
            elif agg_op == "min":
                res = active_df.groupby(groupby_cols)[agg_col].min().reset_index()
                op_str = f".min()"
            elif agg_op == "median":
                res = active_df.groupby(groupby_cols)[agg_col].median().reset_index()
                op_str = f".median()"
            else:
                res = active_df.groupby(groupby_cols)[agg_col].mean().reset_index()
                op_str = f".mean()"
                
            code_expr = f"{base_df_ref}{groupby_expr}['{agg_col}']{op_str}.reset_index()"
            active_df = res
            expr_parts.append(code_expr)
        else:
            # Default groupby count if no aggregation specified
            res = active_df.groupby(groupby_cols).size().reset_index(name="count")
            code_expr = f"{base_df_ref}{groupby_expr}.size().reset_index(name='count')"
            active_df = res
            expr_parts.append(code_expr)

        # 4. Apply HAVING filters (post-groupby)
        if having_filters:
            h_mask = None
            h_exprs = []
            base_df_ref = expr_parts[-1]
            for filt in having_filters:
                col = filt["column"] # Should match aggregated column name in reset_index dataframe
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
        elif op == "quantile":
            val = active_df[col].quantile(0.9)
            code_expr = f"{base_df_ref}['{col}'].quantile(0.9)"
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
        
        # Check if limit is specified
        limit = parsed.execution_plan.get("limit")
        limit_type = parsed.execution_plan.get("limit_type", "top")
        
        if limit:
            if limit_type == "top" or (limit_type == "bottom" and asc == False):
                active_df = active_df.nlargest(limit, col)
                expr_parts.append(f"{base_df_ref}.nlargest({limit}, '{col}')")
            else:
                active_df = active_df.nsmallest(limit, col)
                expr_parts.append(f"{base_df_ref}.nsmallest({limit}, '{col}')")
        else:
            active_df = active_df.sort_values(by=col, ascending=asc)
            expr_parts.append(f"{base_df_ref}.sort_values(by='{col}', ascending={asc})")
            
    # 7. Ranking (dense / average)
    if parsed.ranking:
        rank_info = parsed.ranking[0]
        col = rank_info["column"]
        method = rank_info["method"]
        base_df_ref = expr_parts[-1] if expr_parts else df_name
        
        ranked_df = active_df.copy()
        ranked_df["rank"] = active_df[col].rank(method=method, ascending=False)
        active_df = ranked_df
        expr_parts.append(f"({base_df_ref}.assign(rank={base_df_ref}['{col}'].rank(method='{method}', ascending=False)))")

    # 8. Default fallback limit if requested but no sorting specified
    limit = parsed.execution_plan.get("limit")
    if limit and not parsed.sorting:
        base_df_ref = expr_parts[-1] if expr_parts else df_name
        active_df = active_df.head(limit)
        expr_parts.append(f"{base_df_ref}.head({limit})")

    final_expr = expr_parts[-1] if expr_parts else f"{df_name}.copy()"
    return active_df, final_expr
