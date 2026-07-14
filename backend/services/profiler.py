import os
import json
import pandas as pd
import backend.config as config
from backend.services.loader import DATA_DIR

PROFILES_DIR = os.path.join(DATA_DIR, "profiles")

def get_df_hash(df: pd.DataFrame) -> str:
    """
    Computes a stable hash representation of a dataframe based on its shape and columns.
    """
    col_str = ",".join(df.columns)
    return f"{col_str}:{df.shape[0]}x{df.shape[1]}"

def profile_dataset(name: str, df: pd.DataFrame) -> str:
    """
    Generates a statistical profile of a dataframe and caches it.
    """
    os.makedirs(PROFILES_DIR, exist_ok=True)
    df_hash = get_df_hash(df)
    profile_path = os.path.join(PROFILES_DIR, f"{name}_{df_hash}.json")
    
    # Try reading from cache
    if os.path.exists(profile_path):
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass

    # Build profile dict
    profile = {
        "dataset_name": name,
        "rows": df.shape[0],
        "columns_count": df.shape[1],
        "columns": []
    }
    
    # Analyze columns
    for col in df.columns:
        col_type = str(df[col].dtype)
        null_count = int(df[col].isnull().sum())
        null_pct = round((null_count / len(df)) * 100, 2) if len(df) > 0 else 0
        unique_count = int(df[col].nunique())
        
        col_stats = {
            "name": col,
            "type": col_type,
            "null_percentage": null_pct,
            "unique_count": unique_count
        }
        
        # Numeric Stats
        if pd.api.types.is_numeric_dtype(df[col]) and not df[col].empty:
            col_stats["min"] = float(df[col].min()) if not pd.isnull(df[col].min()) else None
            col_stats["max"] = float(df[col].max()) if not pd.isnull(df[col].max()) else None
            col_stats["mean"] = float(df[col].mean()) if not pd.isnull(df[col].mean()) else None
            col_stats["median"] = float(df[col].median()) if not pd.isnull(df[col].median()) else None
        
        # Top Values (up to 3)
        try:
            top_vals = df[col].value_counts().head(3)
            col_stats["top_values"] = [{"value": str(k), "count": int(v)} for k, v in top_vals.items()]
        except Exception:
            col_stats["top_values"] = []
            
        profile["columns"].append(col_stats)

    # Core correlations (top numeric correlation pairs if numerical columns exist)
    try:
        numeric_cols = df.select_dtypes(include=["number"])
        if numeric_cols.shape[1] >= 2:
            corr_matrix = numeric_cols.corr()
            correlations = []
            cols_list = corr_matrix.columns.tolist()
            for i in range(len(cols_list)):
                for j in range(i+1, len(cols_list)):
                    val = corr_matrix.iloc[i, j]
                    if not pd.isnull(val) and abs(val) > 0.3:
                        correlations.append(f"{cols_list[i]} & {cols_list[j]} (r={val:.2f})")
            profile["high_correlations"] = correlations[:5]
    except Exception:
        pass

    profile_str = json.dumps(profile, indent=2)
    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(profile_str)
    except Exception:
        pass
        
    return profile_str

def format_profile_for_prompt(profile_str: str) -> str:
    """
    Transforms the JSON profile output into a concise markdown text summary for LLM prompt ingestion.
    """
    try:
        profile = json.loads(profile_str)
        summary = f"Dataset: {profile['dataset_name']} ({profile['rows']} rows, {profile['columns_count']} columns)\nColumn Details:\n"
        for col in profile["columns"]:
            details = f"- {col['name']} ({col['type']}): Null%={col['null_percentage']}%, Unique={col['unique_count']}"
            if "min" in col and col["min"] is not None:
                details += f", Min={col['min']}, Max={col['max']}, Mean={col['mean']:.2f}"
            if col.get("top_values"):
                tops = ", ".join([f"'{v['value']}' ({v['count']})" for v in col["top_values"][:2]])
                details += f", Top=[{tops}]"
            summary += details + "\n"
        if profile.get("high_correlations"):
            summary += "Correlations: " + ", ".join(profile["high_correlations"]) + "\n"
        return summary
    except Exception as e:
        return f"Error formatting profile: {str(e)}"
