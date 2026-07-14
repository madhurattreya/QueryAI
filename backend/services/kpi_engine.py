import pandas as pd
import backend.config as config
from backend.services.analytics_lib import calculate_growth_rate

# Global in-memory cache for computed KPIs
# Key: dataset_hash, Value: KPI dict
kpi_cache = {}

def get_kpi_cache():
    return kpi_cache

def resolve_column_by_semantic_synonyms(df: pd.DataFrame, synonyms: list) -> str | None:
    """
    Finds the first column in DataFrame matching any of the synonyms (case-insensitive).
    """
    for synonym in synonyms:
        syn_lower = synonym.lower()
        # Case-insensitive exact match
        for col in df.columns:
            if col.lower() == syn_lower:
                return col
        # Substring match fallback
        for col in df.columns:
            if syn_lower in col.lower():
                return col
    return None

def compute_and_cache_kpis(dataset_name: str, df: pd.DataFrame, dataset_hash: str):
    """
    Precomputes standard business KPIs for the active dataset and caches them.
    """
    if df is None or df.empty:
        return
        
    # Resolve columns semantically
    sales_col = resolve_column_by_semantic_synonyms(df, ["sales", "revenue", "amount", "turnover", "income"])
    profit_col = resolve_column_by_semantic_synonyms(df, ["profit", "earnings", "margin", "gain"])
    orders_col = resolve_column_by_semantic_synonyms(df, ["order id", "order_id", "orderid", "transaction", "orders"])
    customers_col = resolve_column_by_semantic_synonyms(df, ["customer id", "customer_id", "customer name", "customer"])
    products_col = resolve_column_by_semantic_synonyms(df, ["product id", "product_name", "product", "item"])
    region_col = resolve_column_by_semantic_synonyms(df, ["region", "state", "city", "location"])
    category_col = resolve_column_by_semantic_synonyms(df, ["category", "department", "segment"])
    date_col = resolve_column_by_semantic_synonyms(df, ["date", "order date", "joined", "hired"])

    # Base dictionary
    kpis = {
        "dataset_name": dataset_name,
        "total_rows": len(df),
        "revenue": 0.0,
        "profit": 0.0,
        "margin": 0.0,
        "orders": 0,
        "customers": 0,
        "products": 0,
        "aov": 0.0,
        "growth": None,
        "top_regions": [],
        "top_categories": [],
        "top_customers": []
    }

    try:
        # Sales & Profit KPIs
        if sales_col:
            kpis["revenue"] = float(df[sales_col].sum())
        if profit_col:
            kpis["profit"] = float(df[profit_col].sum())
        if sales_col and profit_col and kpis["revenue"] > 0:
            kpis["margin"] = round((kpis["profit"] / kpis["revenue"]) * 100, 2)
            
        # Orders, Customers, Products counts
        if orders_col:
            kpis["orders"] = int(df[orders_col].nunique())
        else:
            kpis["orders"] = len(df)
            
        if customers_col:
            kpis["customers"] = int(df[customers_col].nunique())
        if products_col:
            kpis["products"] = int(df[products_col].nunique())
            
        # Average Order Value
        if kpis["revenue"] > 0 and kpis["orders"] > 0:
            kpis["aov"] = round(kpis["revenue"] / kpis["orders"], 2)
            
        # Growth
        if date_col and sales_col:
            try:
                growth_df = calculate_growth_rate(df, date_col, sales_col, 'YoY')
                if len(growth_df) >= 2:
                    kpis["growth"] = round(float(growth_df['Growth'].iloc[-1]) * 100, 2)
            except Exception:
                pass
                
        # Top breakdowns
        if region_col and sales_col:
            top_regions = df.groupby(region_col)[sales_col].sum().nlargest(3)
            kpis["top_regions"] = [{"Region": str(k), "Sales": float(v)} for k, v in top_regions.items()]
            
        if category_col and sales_col:
            top_categories = df.groupby(category_col)[sales_col].sum().nlargest(3)
            kpis["top_categories"] = [{"Category": str(k), "Sales": float(v)} for k, v in top_categories.items()]
            
        if customers_col and sales_col:
            top_customers = df.groupby(customers_col)[sales_col].sum().nlargest(5)
            kpis["top_customers"] = [{"Customer": str(k), "Sales": float(v)} for k, v in top_customers.items()]
            
    except Exception as e:
        print(f"[KPI ENGINE ERROR] Failed to calculate KPIs: {str(e)}")

    kpi_cache[dataset_hash] = kpis
    return kpis

def is_kpi_dashboard_query(question: str) -> bool:
    """
    Checks if user is requesting a dashboard overview or business snapshot.
    """
    q_clean = question.lower().strip()
    kpi_keywords = ["show dashboard", "dashboard", "summary", "overview", "business snapshot", "business summary", "kpi summary"]
    return any(kw in q_clean for kw in kpi_keywords)
