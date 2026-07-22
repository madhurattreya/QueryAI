import sys
import os
import pandas as pd

# Adjust sys path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.config as config
from backend.services.router import classify_query_engine_detailed
from backend.services.schema_index import SchemaIndexRegistry
import backend.services.history_db as db
import backend.services.kpi_engine as kpi_engine

def test_stability_gate():
    print("============================================================")
    print("               RUNNING DETERMINISTIC STABILITY GATE")
    print("============================================================")
    
    # 1. Setup Mock Dataset
    mock_df = pd.DataFrame({
        "Order ID": [101, 102, 103],
        "Category": ["Furniture", "Technology", "Office Supplies"],
        "Sales": [1500, 3000, 800],
        "Profit": [150, 600, 80]
    })
    
    config.datasets.clear()
    config.datasets["Superstore"] = mock_df
    config.current_source_type = "file"
    SchemaIndexRegistry.build_or_refresh("Superstore", mock_df)
    
    db.init_db()
    
    queries = [
        "Total Sales",
        "average order value each Category",
        "sales where Profit > 100"
    ]
    
    iterations = 100
    
    for q in queries:
        print(f"Testing Query: '{q}' over {iterations} iterations...")
        
        baseline_res = classify_query_engine_detailed(q)
        baseline_engine = baseline_res["engine"]
        baseline_parsed = baseline_res["parsed_query"]
        
        # Extract baseline plans
        baseline_plan = baseline_parsed.execution_plan if baseline_parsed else None
        baseline_confidence = baseline_parsed.confidence if baseline_parsed else 0.0
        
        for i in range(1, iterations):
            current_res = classify_query_engine_detailed(q)
            current_engine = current_res["engine"]
            current_parsed = current_res["parsed_query"]
            current_plan = current_parsed.execution_plan if current_parsed else None
            current_confidence = current_parsed.confidence if current_parsed else 0.0
            
            # Assert identity
            assert current_engine == baseline_engine, f"Engine mismatch at iter {i}: {current_engine} vs {baseline_engine}"
            assert current_confidence == baseline_confidence, f"Confidence mismatch at iter {i}: {current_confidence} vs {baseline_confidence}"
            
            if baseline_plan is not None:
                assert current_plan is not None, f"Plan missing at iter {i}"
                assert current_plan.get("intent") == baseline_plan.get("intent"), f"Intent mismatch at iter {i}"
                assert current_plan.get("aggregations") == baseline_plan.get("aggregations"), f"Aggregations mismatch at iter {i}"
                assert current_plan.get("filters") == baseline_plan.get("filters"), f"Filters mismatch at iter {i}"
                assert current_plan.get("groupby") == baseline_plan.get("groupby"), f"Groupby mismatch at iter {i}"
                assert current_plan.get("sorting") == baseline_plan.get("sorting"), f"Sorting mismatch at iter {i}"
                assert current_plan.get("matched_columns") == baseline_plan.get("matched_columns"), f"Matched columns mismatch at iter {i}"
                assert current_plan.get("dsl") == baseline_plan.get("dsl"), f"DSL expression mismatch at iter {i}"
                
        print(f"  Query '{q}': STABLE (100/100 matching runs)")
        
    print("Deterministic Stability Gate: PASSED SUCCESSFULLY!")
    print("============================================================\n")

if __name__ == "__main__":
    test_stability_gate()
