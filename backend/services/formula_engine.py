import re
import pandas as pd
import numpy as np

class FormulaEngine:
    def parse_and_translate_expression(self, expr: str, df_var_name: str = "df") -> str:
        """
        Translates a DAX-like formula string into a executable Python/Pandas expression.
        Examples:
          "SUM(Sales) / COUNT(Order ID)" -> "df['Sales'].sum() / df['Order ID'].count()"
          "DIVIDE(SUM(Profit), SUM(Sales))" -> "df['Profit'].sum() / df['Sales'].sum()"
          "RUNNING_TOTAL(Sales)" -> "df['Sales'].cumsum()"
          "MOVING_AVERAGE(Sales, 3)" -> "df['Sales'].rolling(3, min_periods=1).mean()"
        """
        expr_clean = expr.strip()

        # Handle DIVIDE(a, b) -> (a) / (b)
        divide_match = re.match(r"^DIVIDE\((.*),(.*)\)$", expr_clean, re.IGNORECASE)
        if divide_match:
            part_a = self.parse_and_translate_expression(divide_match.group(1).strip(), df_var_name)
            part_b = self.parse_and_translate_expression(divide_match.group(2).strip(), df_var_name)
            return f"({part_a}) / ({part_b})"

        # Handle Window Functions / Time Intelligence
        running_total_match = re.match(r"^RUNNING_TOTAL\((.*?)\)$", expr_clean, re.IGNORECASE)
        if running_total_match:
            col = running_total_match.group(1).strip()
            return f"{df_var_name}['{col}'].cumsum()"

        moving_avg_match = re.match(r"^MOVING_AVERAGE\((.*?),\s*(\d+)\)$", expr_clean, re.IGNORECASE)
        if moving_avg_match:
            col = moving_avg_match.group(1).strip()
            window = moving_avg_match.group(2).strip()
            return f"{df_var_name}['{col}'].rolling({window}, min_periods=1).mean()"

        rank_match = re.match(r"^RANK\((.*?)\)$", expr_clean, re.IGNORECASE)
        if rank_match:
            col = rank_match.group(1).strip()
            return f"{df_var_name}['{col}'].rank(ascending=False)"

        dense_rank_match = re.match(r"^DENSE_RANK\((.*?)\)$", expr_clean, re.IGNORECASE)
        if dense_rank_match:
            col = dense_rank_match.group(1).strip()
            return f"{df_var_name}['{col}'].rank(method='dense', ascending=False)"

        percentile_match = re.match(r"^PERCENTILE\((.*?),\s*([0-9\.]+)\)$", expr_clean, re.IGNORECASE)
        if percentile_match:
            col = percentile_match.group(1).strip()
            pct = percentile_match.group(2).strip()
            return f"{df_var_name}['{col}'].quantile({pct})"

        # Standard aggregate functions
        funcs_map = {
            r"\bSUM\((.*?)\)": f"{df_var_name}['\\1'].sum()",
            r"\bAVERAGE\((.*?)\)": f"{df_var_name}['\\1'].mean()",
            r"\bCOUNT\((.*?)\)": f"{df_var_name}['\\1'].count()",
            r"\bMAX\((.*?)\)": f"{df_var_name}['\\1'].max()",
            r"\bMIN\((.*?)\)": f"{df_var_name}['\\1'].min()",
            r"\bMEDIAN\((.*?)\)": f"{df_var_name}['\\1'].median()"
        }

        translated = expr_clean
        for pattern, repl in funcs_map.items():
            # Apply regex replacements iteratively
            translated = re.sub(pattern, repl, translated, flags=re.IGNORECASE)

        # If it doesn't match standard aggregation, treat as row-level calculated column evaluation
        if df_var_name in translated:
            return translated

        # Calculated column fallback: e.g. "Profit / Sales" -> "df['Profit'] / df['Sales']"
        # Match word tokens that are not numerical and not functions/operators
        words = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_\s]*)\b", translated))
        # Exclude python keywords and pandas attributes
        ignored_words = {"sum", "mean", "count", "max", "min", "median", "cumsum", "rolling", "rank", "quantile", "df", "pd", "np", "and", "or", "not"}
        for word in words:
            word_clean = word.strip()
            if word_clean.lower() not in ignored_words:
                translated = re.sub(r'\b' + re.escape(word) + r'\b', f"{df_var_name}['{word_clean}']", translated)
                
        return translated

    def evaluate_calculated_column(self, df: pd.DataFrame, expr: str) -> pd.Series:
        """
        Evaluates row-level calculated columns on a DataFrame.
        """
        try:
            py_expr = self.parse_and_translate_expression(expr, "df")
            local_vars = {"df": df, "np": np}
            return eval(py_expr, {"__builtins__": {}}, local_vars)
        except Exception as e:
            raise ValueError(f"Failed to evaluate calculated column: {str(e)}")

    def evaluate_calculated_measure(self, df: pd.DataFrame, expr: str) -> any:
        """
        Evaluates aggregated business measures on a DataFrame.
        """
        try:
            py_expr = self.parse_and_translate_expression(expr, "df")
            local_vars = {"df": df, "np": np}
            return eval(py_expr, {"__builtins__": {}}, local_vars)
        except Exception as e:
            raise ValueError(f"Failed to evaluate calculated measure: {str(e)}")
