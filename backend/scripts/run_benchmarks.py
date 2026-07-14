import sys
import os
import time
import pandas as pd
import json

# Adjust sys path to run script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.config as config
from backend.services.query_parser import parse_question
from backend.services.router import classify_query_engine_detailed
from backend.services.query_engine import execute_parsed_query
import backend.services.kpi_engine as kpi_engine

def run_suite():
    print("============================================================")
    # 1. Setup Mock Dataset
    mock_df = pd.DataFrame({
        "Order ID": [101, 102, 103, 104, 105, 106, 107, 108],
        "City": ["Delhi", "Delhi", "Mumbai", "Mumbai", "Delhi", "Mumbai", "Bangalore", "Bangalore"],
        "Category": ["Furniture", "Technology", "Furniture", "Office Supplies", "Furniture", "Technology", "Office Supplies", "Furniture"],
        "Sales": [1500, 3000, 2500, 800, 1200, 4500, 600, 1100],
        "Profit": [150, 600, 500, 80, 100, 900, 60, 110],
        "Order Date": pd.to_datetime([
            "2023-01-10", "2023-01-15", "2023-01-20", "2023-02-10",
            "2023-02-15", "2023-02-20", "2023-03-01", "2023-03-10"
        ])
    })
    
    config.datasets["Superstore"] = mock_df
    config.current_source_type = "file"
    dataset_hash = "mock_superstore_hash"
    
    # Pre-compute KPIs
    kpi_engine.compute_and_cache_kpis("Superstore", mock_df, dataset_hash)
    print("[INIT] Mock dataset Superstore loaded & KPI Cache computed.")
    print("============================================================\n")

    # 2. Benchmark Cases
    test_cases = [
        {"q": "Show sales in Delhi", "expected_intent": "deterministic"},
        {"q": "Only Furniture", "expected_intent": "deterministic"}, # context follow-up
        {"q": "Which city has most profit", "expected_intent": "deterministic"},
        {"q": "Order ID 103", "expected_intent": "id_lookup"},
        {"q": "Which city has most profitt", "expected_intent": "deterministic"}, # typo test
        {"q": "Delhi ka profit dikhao", "expected_intent": "deterministic"}, # Hinglish test
        {"q": "Show monthly trend", "expected_intent": "deterministic"}, # trend test
        {"q": "Second highest sales", "expected_intent": "deterministic"}, # offset test
    ]

    passed_count = 0
    total_latency = 0.0
    
    prev_plan = None
    
    for idx, case in enumerate(test_cases):
        q = case["q"]
        expected = case["expected_intent"]
        
        t_start = time.time()
        router_res = classify_query_engine_detailed(q, prev_plan=prev_plan)
        engine_type = router_res["engine"]
        parsed = router_res["parsed_query"]
        prev_plan = parsed.execution_plan if parsed else None
        
        latency = (time.time() - t_start) * 1000 # in ms
        total_latency += latency
        
        # Verify query engine execution
        result, _ = execute_parsed_query(parsed, mock_df, "Superstore")
        
        # Output results
        is_matched = (
            engine_type == expected or 
            (expected == "deterministic" and engine_type in ["deterministic", "analytics_lib", "visualization"])
        )
        status = "PASSED" if is_matched else "FAILED"
        if status == "PASSED":
            passed_count += 1
            
        print(f"Test #{idx+1}: '{q}'")
        print(f"  Routed Engine : {engine_type} (Expected: {expected})")
        print(f"  Latency       : {latency:.2f} ms")
        print(f"  Rows Returned : {len(result) if isinstance(result, pd.DataFrame) else 1}")
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

if __name__ == "__main__":
    run_suite()
