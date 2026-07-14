import os
import json
import pandas as pd
import backend.config as config
from backend.services.loader import DATA_DIR

PROFILES_DIR = os.path.join(DATA_DIR, "profiles")

SEMANTIC_TEMPLATES = {
    "sales": {
        "business_name": "Sales",
        "display_name": "Revenue",
        "aggregation_type": "sum",
        "description": "Total sales revenue from transactions",
        "units": "$",
        "synonyms": ["revenue", "sales", "turnover", "income", "amount", "sold amount", "sale", "sale price", "billing", "earnings"]
    },
    "profit": {
        "business_name": "Profit",
        "display_name": "Profit",
        "aggregation_type": "sum",
        "description": "Net business earnings after costs",
        "units": "$",
        "synonyms": ["earnings", "profit", "net profit", "gain", "margin", "income", "earning", "profitability"]
    },
    "quantity": {
        "business_name": "Quantity",
        "display_name": "Quantity Sold",
        "aggregation_type": "sum",
        "description": "Total number of units sold",
        "units": "units",
        "synonyms": ["quantity", "qty", "volume", "units", "items count", "sold quantity", "count", "pieces"]
    },
    "discount": {
        "business_name": "Discount",
        "display_name": "Discount Rate",
        "aggregation_type": "mean",
        "description": "Promotional discount applied to price",
        "units": "%",
        "synonyms": ["discount", "disc", "rebate", "markdown", "cut", "discount percentage"]
    },
    "order id": {
        "business_name": "Order ID",
        "display_name": "Order ID",
        "aggregation_type": "count",
        "description": "Unique identifier of customer order transaction",
        "units": "ID",
        "synonyms": ["order id", "order", "transaction id", "orderid", "purchase id", "transactions", "orders", "txn id", "bill no"]
    },
    "customer name": {
        "business_name": "Customer Name",
        "display_name": "Customer",
        "aggregation_type": "count",
        "description": "Full name of customer",
        "units": "Name",
        "synonyms": ["customer name", "customer", "buyer", "client name", "client", "patron", "customers", "customer_name", "client_name"]
    },
    "product name": {
        "business_name": "Product Name",
        "display_name": "Product",
        "aggregation_type": "count",
        "description": "Description/name of the product",
        "units": "Name",
        "synonyms": ["product name", "product", "item name", "item", "merchandise", "products", "sku", "product_name", "product id"]
    },
    "city": {
        "business_name": "City",
        "display_name": "City",
        "aggregation_type": "count",
        "description": "City where transaction was completed",
        "units": "Location",
        "synonyms": ["city", "town", "metro", "cities", "location city", "shipped city"]
    },
    "state": {
        "business_name": "State",
        "display_name": "State",
        "aggregation_type": "count",
        "description": "State where transaction occurred",
        "units": "Location",
        "synonyms": ["state", "province", "territory", "states", "shipped state"]
    },
    "region": {
        "business_name": "Region",
        "display_name": "Region",
        "aggregation_type": "count",
        "description": "Geographical region partition",
        "units": "Location",
        "synonyms": ["region", "zone", "area", "regions", "geography"]
    },
    "category": {
        "business_name": "Category",
        "display_name": "Category",
        "aggregation_type": "count",
        "description": "High level product classification category",
        "units": "Category",
        "synonyms": ["category", "dept", "department", "division", "categories", "vertical", "product group"]
    },
    "salary": {
        "business_name": "Salary",
        "display_name": "Salary",
        "aggregation_type": "mean",
        "description": "Employee annual compensation",
        "units": "$",
        "synonyms": ["salary", "wage", "pay", "compensation", "earnings", "payroll"]
    }
}

def get_df_hash(df: pd.DataFrame) -> str:
    col_str = ",".join(df.columns)
    return f"{col_str}:{df.shape[0]}x{df.shape[1]}"

def profile_dataset(name: str, df: pd.DataFrame) -> str:
    """
    Generates a statistical profile of a dataframe (including a rich Semantic Layer) and caches it.
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
        "columns": [],
        "semantic_layer": {}
    }
    
    # Analyze columns & construct Semantic Layer
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
        
        # Sample Values (up to 3)
        sample_vals = []
        try:
            non_null_vals = df[col].dropna().unique()
            sample_vals = [str(x) for x in non_null_vals[:3]]
            col_stats["top_values"] = [{"value": str(k), "count": int(v)} for k, v in df[col].value_counts().head(3).items()]
        except Exception:
            col_stats["top_values"] = []
            
        profile["columns"].append(col_stats)

        # Build Semantic Layer entry for this column
        col_lower = col.lower().strip()
        matched_template = None
        
        # Check template matching
        for key, template in SEMANTIC_TEMPLATES.items():
            if key in col_lower or any(syn in col_lower for syn in template["synonyms"]):
                matched_template = template
                break
                
        # Default fallback semantic entry
        if pd.api.types.is_numeric_dtype(df[col]):
            data_type = "numeric"
            default_agg = "mean" if "discount" in col_lower or "average" in col_lower or "rate" in col_lower else "sum"
        elif pd.api.types.is_datetime64_any_dtype(df[col]) or "date" in col_lower or "time" in col_lower:
            data_type = "datetime"
            default_agg = "count"
        else:
            data_type = "string"
            default_agg = "count"

        semantic_entry = {
            "business_name": col,
            "actual_column": col,
            "display_name": col,
            "data_type": data_type,
            "aggregation_type": default_agg,
            "description": f"Column {col} containing {data_type} data",
            "units": "units" if data_type == "numeric" else "count",
            "sample_values": sample_vals,
            "synonyms": [col_lower, col_lower.replace("_", " "), col_lower.replace(" ", "")]
        }

        if matched_template:
            # Enrich entry with matched template details
            semantic_entry["business_name"] = matched_template["business_name"]
            semantic_entry["display_name"] = matched_template["display_name"]
            semantic_entry["aggregation_type"] = matched_template["aggregation_type"]
            semantic_entry["description"] = matched_template["description"]
            semantic_entry["units"] = matched_template["units"]
            semantic_entry["synonyms"] = list(set(semantic_entry["synonyms"] + matched_template["synonyms"]))

        profile["semantic_layer"][col] = semantic_entry

    # Core correlations
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
            
        # Append semantic layer info
        if "semantic_layer" in profile and profile["semantic_layer"]:
            summary += "\nSemantic Layer Glossary:\n"
            for col, sem in profile["semantic_layer"].items():
                summary += f"  * {col} (as '{sem['display_name']}'): {sem['description']}. Synonyms: {', '.join(sem['synonyms'][:4])}\n"
                
        if profile.get("high_correlations"):
            summary += "Correlations: " + ", ".join(profile["high_correlations"]) + "\n"
        return summary
    except Exception as e:
        return f"Error formatting profile: {str(e)}"
