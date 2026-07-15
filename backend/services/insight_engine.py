import os
import pandas as pd
import numpy as np

def generate_dataset_insights(df_name: str, df: pd.DataFrame) -> str:
    """
    AI Insight Engine 2.0. Computes detailed facts programmatically (growth, contributors, 
    variance, seasonality, anomalies, correlations) and uses LLM only to polish the prose.
    """
    if df is None or df.empty:
        return "No active dataset loaded for insights analysis."
        
    raw_facts = []
    rows, cols = df.shape
    raw_facts.append(f"Dataset Size: {rows} rows and {cols} columns.")

    num_cols = df.select_dtypes(include=["number"]).columns.tolist()
    cat_cols = [c for c in df.columns if df[c].dtype == 'object' or isinstance(df[c].dtype, pd.CategoricalDtype)]
    
    date_cols = []
    for c in df.columns:
        if "date" in c.lower() or "joined" in c.lower() or "hired" in c.lower() or "year" in c.lower():
            try:
                pd.to_datetime(df[c].head(5), errors="raise")
                date_cols.append(c)
            except Exception:
                pass

    # 1. Top Contributor
    if cat_cols and num_cols:
        try:
            cat_col = cat_cols[0]
            val_col = num_cols[0]
            grouped = df.groupby(cat_col)[val_col].sum().sort_values(ascending=False)
            total = grouped.sum()
            if total > 0:
                top_pct = grouped.head(1).values[0] / total
                raw_facts.append(f"Top Contributor: Category '{grouped.index[0]}' in column '{cat_col}' represents {top_pct * 100:.2f}% of total {val_col}.")
        except Exception:
            pass

    # 2. Growth Rates (Fastest growth / Worst decline)
    if date_cols and num_cols:
        try:
            date_col = date_cols[0]
            val_col = num_cols[0]
            temp = df.copy()
            temp["__date"] = pd.to_datetime(temp[date_col], errors="coerce")
            temp = temp.dropna(subset=["__date"]).sort_values("__date")
            temp["__period"] = temp["__date"].dt.to_period("M")
            monthly = temp.groupby("__period")[val_col].sum()
            if len(monthly) >= 2:
                pct_change = monthly.pct_change() * 100
                fastest = pct_change.idxmax()
                fastest_val = pct_change.max()
                worst = pct_change.idxmin()
                worst_val = pct_change.min()
                if not pd.isnull(fastest_val):
                    raw_facts.append(f"Fastest Growth: In {fastest}, {val_col} grew by {fastest_val:.2f}% month-over-month.")
                if not pd.isnull(worst_val):
                    raw_facts.append(f"Worst Decline: In {worst}, {val_col} declined by {worst_val:.2f}% month-over-month.")
        except Exception:
            pass

    # 3. High Variance
    for col in num_cols[:2]:
        col_series = pd.to_numeric(df[col], errors="coerce").dropna()
        if col_series.empty:
            continue
        mean = col_series.mean()
        std = col_series.std()
        if mean > 0:
            cv = std / mean
            if cv > 0.5:
                raw_facts.append(f"High Variance: Column '{col}' has high relative variance with coefficient of variation = {cv:.2f} (std = {std:.2f}, mean = {mean:.2f}).")

    # 4. Seasonality
    if date_cols and num_cols:
        try:
            date_col = date_cols[0]
            val_col = num_cols[0]
            temp = df.copy()
            temp["__date"] = pd.to_datetime(temp[date_col], errors="coerce")
            temp = temp.dropna(subset=["__date"])
            temp["__month"] = temp["__date"].dt.month
            monthly_agg = temp.groupby("__month")[val_col].sum()
            if len(monthly_agg) >= 3:
                cv = monthly_agg.std() / monthly_agg.mean()
                if cv > 0.3:
                    raw_facts.append(f"Seasonality: Column '{val_col}' exhibits seasonal behavior (cv = {cv:.2f}) with peak month {monthly_agg.idxmax()} and trough month {monthly_agg.idxmin()}.")
        except Exception:
            pass

    # 5. Anomalies & Outliers
    for col in num_cols[:2]:
        col_series = pd.to_numeric(df[col], errors="coerce").dropna()
        if col_series.empty:
            continue
        q1 = col_series.quantile(0.25)
        q3 = col_series.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = col_series[(col_series < lower) | (col_series > upper)]
        if len(outliers) > 0:
            raw_facts.append(f"Anomalies: Column '{col}' contains {len(outliers)} statistical outliers (outlier percentage: {len(outliers)/len(col_series)*100:.2f}%) with values beyond limits [{lower:.2f}, {upper:.2f}].")

    # 6. Correlations
    if len(num_cols) >= 2:
        try:
            corr_matrix = df[num_cols].corr()
            for i in range(len(num_cols)):
                for j in range(i + 1, len(num_cols)):
                    r = corr_matrix.iloc[i, j]
                    if abs(r) > 0.5 and not np.isnan(r):
                        raw_facts.append(f"Correlation: Strong correlation detected between '{num_cols[i]}' and '{num_cols[j]}' (Pearson r = {r:.2f}).")
        except Exception:
            pass

    # Business Recommendations compilation
    recommendations = []
    if any("Anomaly" in f or "outlier" in f.lower() for f in raw_facts):
        recommendations.append("Audit transactions producing values outside IQR bounds.")
    if any("Variance" in f for f in raw_facts):
        recommendations.append("Apply rolling averages or stabilize supply chains to mitigate high variance.")
    if any("Decline" in f for f in raw_facts):
        recommendations.append("Investigate the root cause of the worst monthly drops in volume.")
    if not recommendations:
        recommendations.append("Regularly check column statistics and data health.")

    raw_facts.append("Business Recommendations: " + ", ".join(recommendations))

    # LLM Rewriting
    raw_insights_text = "\n".join([f"- {fact}" for fact in raw_facts])
    prompt = f"""
You are a Senior Business Intelligence Analyst.
Analyze the following programmatically extracted data quality and business trends:

{raw_insights_text}

Rewrite this into a premium, professional business intelligence report.
Use the following headings:
- **Executive Summary**
- **Deep-Dive Trends & Insights** (mention top contributors, growth rates, correlation, variance, seasonality, anomalies)
- **Actionable Business Recommendations** (align with the findings)

Return only the markdown formatted text. Do not write introductory or concluding remarks.
"""
    from backend.services.llm import LLMManager
    try:
        model = config.settings.get("model", "qwen2.5:7b")
        explanation, _ = LLMManager().call_llm_with_fallback(prompt, model, 0.0)
        return explanation.strip()
    except Exception:
        return "### Executive Summary\n" + raw_insights_text


def run_result_heuristics(df: pd.DataFrame) -> dict:
    """
    Analyzes query result DataFrame for data health heuristics:
    - Outliers (IQR check)
    - Seasonality (monthly coefficient of variation)
    - Anomalies (negative values in strictly positive fields, Z-score outliers)
    - Duplicates
    - Missing values
    """
    if df is None or df.empty:
        return {}

    heuristics = {
        "missing_values": {},
        "duplicates_count": 0,
        "outliers": {},
        "anomalies": [],
        "seasonality": None
    }

    # 1. Missing values
    missing = df.isna().sum().to_dict()
    heuristics["missing_values"] = {k: int(v) for k, v in missing.items() if v > 0}

    # 2. Duplicates
    heuristics["duplicates_count"] = int(df.duplicated().sum())

    # Identify numeric and date columns
    num_cols = df.select_dtypes(include=["number"]).columns.tolist()
    
    date_cols = []
    for c in df.columns:
        if "date" in c.lower() or "joined" in c.lower() or "hired" in c.lower() or "year" in c.lower():
            try:
                pd.to_datetime(df[c].head(5), errors="raise")
                date_cols.append(c)
            except Exception:
                pass

    # 3. Outliers & Negative Value Anomalies
    for col in num_cols:
        col_series = pd.to_numeric(df[col], errors="coerce").dropna()
        if col_series.empty:
            continue
            
        # Strictly positive checks (revenue, profit/sales concentration, quantity)
        if any(kw in col.lower() for kw in ["sales", "revenue", "quantity", "price", "count"]):
            neg_count = int((col_series < 0).sum())
            if neg_count > 0:
                heuristics["anomalies"].append({
                    "column": col,
                    "type": "Negative Values",
                    "description": f"Found {neg_count} negative values in strictly positive field '{col}'."
                })

        # Outlier Detection
        if len(col_series) >= 4:
            q1 = col_series.quantile(0.25)
            q3 = col_series.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                outliers = col_series[(col_series < lower_bound) | (col_series > upper_bound)]
                if len(outliers) > 0:
                    heuristics["outliers"][col] = {
                        "count": len(outliers),
                        "lower_bound": float(lower_bound),
                        "upper_bound": float(upper_bound),
                        "min_outlier": float(outliers.min()),
                        "max_outlier": float(outliers.max())
                    }

    # 4. Seasonality Checks
    if date_cols and num_cols:
        try:
            date_col = date_cols[0]
            val_col = num_cols[0]
            temp_df = df.copy()
            temp_df["__parsed_date"] = pd.to_datetime(temp_df[date_col], errors="coerce")
            temp_df = temp_df.dropna(subset=["__parsed_date"])
            
            if not temp_df.empty:
                temp_df["__month"] = temp_df["__parsed_date"].dt.month
                monthly_agg = temp_df.groupby("__month")[val_col].sum()
                if len(monthly_agg) >= 3:
                    cv = float(monthly_agg.std() / monthly_agg.mean())
                    is_seasonal = cv > 0.3
                    heuristics["seasonality"] = {
                        "coefficient_of_variation": cv,
                        "is_seasonal": is_seasonal,
                        "peak_month": int(monthly_agg.idxmax()),
                        "trough_month": int(monthly_agg.idxmin())
                    }
        except Exception:
            pass

    return heuristics
