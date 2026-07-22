import sys
import os
import time
import pandas as pd
import json
import uuid
from datetime import datetime

# Adjust sys path to run script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.config as config
from backend.services.query_parser import parse_question
from backend.services.router import classify_query_engine_detailed
from backend.services.query_engine import execute_parsed_query
from backend.services.schema_index import SchemaIndexRegistry, SchemaIndex, ColumnEntry, SemanticType
from backend.services.metric_catalog import MetricCatalog, BaseMetricFormula
import backend.services.kpi_engine as kpi_engine
import backend.services.history_db as db
from backend.services.semantic_model import SemanticModelManager

def run_suite():
    print("============================================================")
    print("          QUERYIQ SEMANTIC RECONCILIATION BENCHMARK          ")
    print("============================================================")
    
    # 1. Setup Mock Dataset
    mock_df = pd.DataFrame({
        "Order ID": [101, 102, 103, 104, 105, 106, 107, 108],
        "Customer ID": ["C1", "C2", "C1", "C3", "C2", "C4", "C3", "C1"],
        "Product ID": ["P1", "P2", "P3", "P1", "P2", "P3", "P1", "P2"],
        "City": ["Delhi", "Delhi", "Mumbai", "Mumbai", "Delhi", "Mumbai", "Bangalore", "Bangalore"],
        "Category": ["Furniture", "Technology", "Furniture", "Office Supplies", "Furniture", "Technology", "Office Supplies", "Furniture"],
        "Sales": [1500, 3000, 2500, 800, 1200, 4500, 600, 1100],
        "Profit": [150, 600, 500, 80, 100, 900, 60, 110],
        "Cost": [1350, 2400, 2000, 720, 1100, 3600, 540, 990],
        "Order Date": pd.to_datetime([
            "2023-01-10", "2023-01-15", "2023-01-20", "2023-02-10",
            "2023-02-15", "2023-02-20", "2023-03-01", "2023-03-10"
        ]),
        "Ship Date": pd.to_datetime([
            "2023-01-12", "2023-01-18", "2023-01-22", "2023-02-12",
            "2023-02-18", "2023-02-22", "2023-03-04", "2023-03-12"
        ])
    })
    
    # Initialize SQLite Database
    db.init_db()
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Clean up existing Superstore dataset records to ensure idempotency
    cursor.execute("SELECT id FROM datasets WHERE name = 'Superstore'")
    existing_dataset = cursor.fetchone()
    if existing_dataset:
        dataset_id = existing_dataset["id"]
        cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
        cursor.execute("DELETE FROM semantic_model WHERE dataset_id = ?", (dataset_id,))
    else:
        dataset_id = str(uuid.uuid4())
        
    # Insert new dataset record
    cursor.execute(
        """
        INSERT INTO datasets (id, name, filename, hash, rows, columns, is_active, status, upload_time)
        VALUES (?, ?, ?, ?, ?, ?, 1, 'active', ?)
        """,
        (dataset_id, "Superstore", "superstore.csv", "mock_superstore_hash", len(mock_df), len(mock_df.columns), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    # Insert semantic items
    manager = SemanticModelManager()
    
    # Identifier/Dimension/Measure Overrides
    manager.add_model_item(dataset_id, "Order ID", "dimension", "", category="Identifier", is_measure=0, is_dimension=0)
    manager.add_model_item(dataset_id, "Customer ID", "dimension", "", category="Identifier", is_measure=0, is_dimension=0)
    manager.add_model_item(dataset_id, "Product ID", "dimension", "", category="Identifier", is_measure=0, is_dimension=0)
    
    manager.add_model_item(dataset_id, "City", "dimension", "", category="Dimension", synonyms="town,place,location", is_measure=0, is_dimension=1)
    manager.add_model_item(dataset_id, "Category", "dimension", "", category="Dimension", synonyms="type,class", is_measure=0, is_dimension=1)
    
    manager.add_model_item(dataset_id, "Sales", "measure", "", category="Measure", synonyms="revenue,turnover,sales amount", is_measure=1, is_dimension=0)
    manager.add_model_item(dataset_id, "Profit", "measure", "", category="Measure", synonyms="earnings,gain", is_measure=1, is_dimension=0)
    manager.add_model_item(dataset_id, "Cost", "measure", "", category="Measure", synonyms="expense", is_measure=1, is_dimension=0)
    
    manager.add_model_item(dataset_id, "Order Date", "dimension", "", category="Date", synonyms="order time", is_measure=0, is_dimension=0)
    manager.add_model_item(dataset_id, "Ship Date", "dimension", "", category="Date", synonyms="ship time", is_measure=0, is_dimension=0)
    
    # Calculated Measures
    manager.add_model_item(dataset_id, "average order value", "calculated_measure", "SUM(Sales) / COUNT(Order ID)", display_name="Average Order Value", synonyms="aov", is_measure=1)
    manager.add_model_item(dataset_id, "arpu", "calculated_measure", "SUM(Sales) / COUNT(DISTINCT Customer ID)", display_name="ARPU", is_measure=1)
    manager.add_model_item(dataset_id, "profit margin", "calculated_measure", "SUM(Profit) / SUM(Sales)", display_name="Profit Margin", synonyms="profit_margin", is_measure=1)
    
    # Clear other datasets so Superstore is active
    config.datasets.clear()
    config.datasets["Superstore"] = mock_df
    config.current_source_type = "file"
    dataset_hash = "mock_superstore_hash"
    
    # Register Mock Schema Index
    SchemaIndexRegistry.build_or_refresh("Superstore", mock_df)
    
    # Pre-compute KPIs
    kpi_engine.compute_and_cache_kpis("Superstore", mock_df, dataset_hash)
    print("[INIT] Mock dataset Superstore loaded & Semantic Schema overrides registered.")
    print("============================================================\n")

    # 3. 100 Benchmark Cases across 12 categories
    test_cases = [
        # Category 1: Pure Aggregations (8 cases)
        {"q": "Total Sales", "expected_intent": "deterministic"},
        {"q": "Sum of profit", "expected_intent": "deterministic"},
        {"q": "Average profit", "expected_intent": "deterministic"},
        {"q": "Minimum Sales", "expected_intent": "deterministic"},
        {"q": "Max cost", "expected_intent": "deterministic"},
        {"q": "Total Cost", "expected_intent": "deterministic"},
        {"q": "average Sales", "expected_intent": "deterministic"},
        {"q": "sum profit", "expected_intent": "deterministic"},

        # Category 2: Filter/Selection (10 cases)
        {"q": "Sales in Delhi", "expected_intent": "deterministic"},
        {"q": "Profit where City is Mumbai", "expected_intent": "deterministic"},
        {"q": "Sales for Furniture", "expected_intent": "deterministic"},
        {"q": "Delhi profit", "expected_intent": "deterministic"},
        {"q": "Profit in Mumbai", "expected_intent": "deterministic"},
        {"q": "Sales in Bangalore", "expected_intent": "deterministic"},
        {"q": "Profit where Category is Technology", "expected_intent": "deterministic"},
        {"q": "Sales where Profit > 100", "expected_intent": "deterministic"},
        {"q": "Sales for Office Supplies", "expected_intent": "deterministic"},
        {"q": "Profit in Delhi where Sales > 1000", "expected_intent": "deterministic"},

        # Category 3: Multi-turn context (8 cases)
        {"q": "Show sales in Delhi", "expected_intent": "deterministic", "prev": None},
        {"q": "Only Furniture", "expected_intent": "deterministic", "prev_idx": 18},
        {"q": "Profit > 100", "expected_intent": "deterministic", "prev_idx": 19},
        {"q": "Show sales in Mumbai", "expected_intent": "deterministic", "prev": None},
        {"q": "Only Technology", "expected_intent": "deterministic", "prev_idx": 21},
        {"q": "Cost < 1000", "expected_intent": "deterministic", "prev_idx": 22},
        {"q": "Show sales in Bangalore", "expected_intent": "deterministic", "prev": None},
        {"q": "Only Office Supplies", "expected_intent": "deterministic", "prev_idx": 24},

        # Category 4: Group By (12 cases)
        {"q": "Sales by City", "expected_intent": "deterministic"},
        {"q": "Profit per Category", "expected_intent": "deterministic"},
        {"q": "Total Sales each Category", "expected_intent": "deterministic"},
        {"q": "Profit grouped by City", "expected_intent": "deterministic"},
        {"q": "Turnover according to Category", "expected_intent": "deterministic"},
        {"q": "Earnings City wise", "expected_intent": "deterministic"},
        {"q": "Sales City ke hisaab se", "expected_intent": "deterministic"},
        {"q": "Profit by City and Category", "expected_intent": "deterministic"},
        {"q": "Cost per City", "expected_intent": "deterministic"},
        {"q": "Sales according to City", "expected_intent": "deterministic"},
        {"q": "Turnover Category wise", "expected_intent": "deterministic"},
        {"q": "Earnings town wise", "expected_intent": "deterministic"},

        # Category 5: Distinct Count (10 cases)
        {"q": "Total Customer ID", "expected_intent": "deterministic"},
        {"q": "Unique Customers", "expected_intent": "deterministic"},
        {"q": "Distinct Product ID count", "expected_intent": "deterministic"},
        {"q": "Number of products", "expected_intent": "deterministic"},
        {"q": "Unique Customer Count", "expected_intent": "deterministic"},
        {"q": "Total distinct products", "expected_intent": "deterministic"},
        {"q": "number of customers", "expected_intent": "deterministic"},
        {"q": "distinct Product ID", "expected_intent": "deterministic"},
        {"q": "unique product", "expected_intent": "deterministic"},
        {"q": "Total Customer count", "expected_intent": "deterministic"},

        # Category 6: Calculations (10 cases)
        {"q": "Average Order Value", "expected_intent": "deterministic"},
        {"q": "aov", "expected_intent": "deterministic"},
        {"q": "arpu", "expected_intent": "deterministic"},
        {"q": "profit margin", "expected_intent": "deterministic"},
        {"q": "profit_margin in Delhi", "expected_intent": "deterministic"},
        {"q": "AOV in Mumbai", "expected_intent": "deterministic"},
        {"q": "ARPU in Bangalore", "expected_intent": "deterministic"},
        {"q": "average order value per City", "expected_intent": "deterministic"},
        {"q": "profit margin by Category", "expected_intent": "deterministic"},
        {"q": "AOV town wise", "expected_intent": "deterministic"},

        # Category 7: Lexical matches / synonyms (10 cases)
        {"q": "Total revenue", "expected_intent": "deterministic"},
        {"q": "turnover by town", "expected_intent": "deterministic"},
        {"q": "earnings by class", "expected_intent": "deterministic"},
        {"q": "gain in location", "expected_intent": "deterministic"},
        {"q": "expense each type", "expected_intent": "deterministic"},
        {"q": "total sales amount", "expected_intent": "deterministic"},
        {"q": "average turnover", "expected_intent": "deterministic"},
        {"q": "revenue by class", "expected_intent": "deterministic"},
        {"q": "gain per town", "expected_intent": "deterministic"},
        {"q": "expense by town", "expected_intent": "deterministic"},

        # Category 8: Hinglish / mixed language (10 cases)
        {"q": "Delhi ka total revenue", "expected_intent": "deterministic"},
        {"q": "sales category ke hisaab se", "expected_intent": "deterministic"},
        {"q": "total profit kitna hai", "expected_intent": "deterministic"},
        {"q": "city wise total profit", "expected_intent": "deterministic"},
        {"q": "Delhi me average turnover", "expected_intent": "deterministic"},
        {"q": "Mumbai ka total gain", "expected_intent": "deterministic"},
        {"q": "Furniture class ka cost", "expected_intent": "deterministic"},
        {"q": "total revenue town wise", "expected_intent": "deterministic"},
        {"q": "Mumbai ke hisaab se sales amount", "expected_intent": "deterministic"},
        {"q": "Bangalore ka total turnover", "expected_intent": "deterministic"},

        # Category 9: Ambiguous queries (4 cases)
        {"q": "sales by date", "expected_intent": "deterministic"},
        {"q": "revenue by time", "expected_intent": "deterministic"},
        {"q": "total profit by date", "expected_intent": "deterministic"},
        {"q": "total cost by time", "expected_intent": "deterministic"},

        # Category 10: Superlatives / extremes (8 cases)
        {"q": "highest sales", "expected_intent": "deterministic"},
        {"q": "worst category profit", "expected_intent": "deterministic"},
        {"q": "city with lowest profit", "expected_intent": "deterministic"},
        {"q": "best customer sales", "expected_intent": "deterministic"},
        {"q": "lowest cost", "expected_intent": "deterministic"},
        {"q": "highest profit", "expected_intent": "deterministic"},
        {"q": "best Category", "expected_intent": "deterministic"},
        {"q": "worst City", "expected_intent": "deterministic"},

        # Category 11: Typo resilience (5 cases)
        {"q": "most profitt", "expected_intent": "deterministic"},
        {"q": "town wise saless", "expected_intent": "deterministic"},
        {"q": "unique customres", "expected_intent": "deterministic"},
        {"q": "total revenues", "expected_intent": "deterministic"},
        {"q": "Delhi ka total profitt", "expected_intent": "deterministic"},

        # Category 12: Validation error cases (5 cases)
        {"q": "SUM of City", "expected_intent": "rejection"},
        {"q": "AVG of Category", "expected_intent": "rejection"},
        {"q": "MIN of Customer ID", "expected_intent": "rejection"},
        {"q": "SUM of Product ID", "expected_intent": "rejection"},
        {"q": "AVG of Order Date", "expected_intent": "rejection"}
    ]

    passed_count = 0
    total_latency = 0.0
    plans_memo = {}
    
    for idx, case in enumerate(test_cases):
        q = case["q"]
        expected = case["expected_intent"]
        
        # Resolve multi-turn context
        prev_plan = None
        if "prev_idx" in case:
            prev_plan = plans_memo.get(case["prev_idx"])
            
        t_start = time.time()
        router_res = classify_query_engine_detailed(q, prev_plan=prev_plan)
        engine_type = router_res["engine"]
        parsed = router_res["parsed_query"]
        
        # Save to memo for future context
        plans_memo[idx] = parsed.execution_plan if parsed else None
        
        latency = (time.time() - t_start) * 1000 # in ms
        total_latency += latency
        
        # Execute result (unless rejection expected)
        result_len = 0
        if expected != "rejection" and parsed and parsed.intent not in ("ambiguity", "fallback"):
            try:
                res_val, _ = execute_parsed_query(parsed, mock_df, "Superstore")
                result_len = len(res_val) if isinstance(res_val, pd.DataFrame) else 1
            except Exception as e:
                print(f"  [EXECUTION ERROR] {e}")
                
        # Status verification
        is_matched = False
        if expected == "deterministic":
            is_matched = (engine_type in ["deterministic", "analytics_lib", "visualization"])
        elif expected == "rejection":
            is_matched = (engine_type in ["ambiguity", "llm", "sql"])
            
        status = "PASSED" if is_matched else "FAILED"
        if status == "PASSED":
            passed_count += 1
            
        print(f"Test #{idx+1:03d}: '{q}'")
        print(f"  Routed Engine : {engine_type} (Expected Match: {expected})")
        print(f"  Confidence    : {parsed.confidence if parsed else 0.0:.2f}")
        print(f"  Latency       : {latency:.2f} ms")
        print(f"  Status        : {status}\n")
        
    accuracy = (passed_count / len(test_cases)) * 100
    avg_latency = total_latency / len(test_cases)
    
    print("============================================================")
    print("                    BENCHMARK RESULTS")
    print("============================================================")
    print(f"Total Test Cases : {len(test_cases)}")
    print(f"Passed           : {passed_count}")
    print(f"Accuracy         : {accuracy:.1f}%")
    print(f"Avg Latency      : {avg_latency:.2f} ms")
    print("============================================================")
    
    if passed_count < len(test_cases):
        sys.exit(1)

if __name__ == "__main__":
    run_suite()
