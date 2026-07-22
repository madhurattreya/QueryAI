import os
import sys
import time
import pandas as pd
import json
from datetime import datetime

# Adjust sys path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.config as config
from backend.services.router import classify_query_engine_detailed
from backend.services.schema_index import SchemaIndexRegistry, SemanticType
from backend.services.metric_catalog import MetricCatalog
from backend.services.semantic_model import SemanticModelManager
import backend.services.history_db as db

def setup_all_domains():
    fixture_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures"))
    
    # 1. Load Dataframes
    df_hr = pd.read_csv(os.path.join(fixture_dir, "hr_medium.csv"))
    df_crm = pd.read_csv(os.path.join(fixture_dir, "crm_medium.csv"))
    df_fin = pd.read_csv(os.path.join(fixture_dir, "finance_medium.csv"))
    df_inv = pd.read_csv(os.path.join(fixture_dir, "inventory_medium.csv"))
    
    # Init DB
    db.init_db()
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Clean old
    cursor.execute("DELETE FROM datasets WHERE name IN ('hr', 'crm', 'finance', 'inventory')")
    cursor.execute("DELETE FROM semantic_model")
    
    # Insert datasets
    cursor.execute("INSERT INTO datasets (id, name, filename, hash, rows, columns, is_active, status, upload_time) VALUES ('hr_id', 'hr', 'hr_medium.csv', 'h1', 1000, 5, 0, 'active', ?)", (datetime.now().isoformat(),))
    cursor.execute("INSERT INTO datasets (id, name, filename, hash, rows, columns, is_active, status, upload_time) VALUES ('crm_id', 'crm', 'crm_medium.csv', 'c1', 1000, 5, 0, 'active', ?)", (datetime.now().isoformat(),))
    cursor.execute("INSERT INTO datasets (id, name, filename, hash, rows, columns, is_active, status, upload_time) VALUES ('fin_id', 'finance', 'finance_medium.csv', 'f1', 1000, 5, 0, 'active', ?)", (datetime.now().isoformat(),))
    cursor.execute("INSERT INTO datasets (id, name, filename, hash, rows, columns, is_active, status, upload_time) VALUES ('inv_id', 'inventory', 'inventory_medium.csv', 'i1', 1000, 5, 1, 'active', ?)", (datetime.now().isoformat(),))
    conn.commit()
    conn.close()
    
    # Overrides
    manager = SemanticModelManager()
    
    # HR
    manager.add_model_item("hr_id", "Employee ID", "dimension", "", category="Identifier", synonyms="emp id,staff id", is_measure=0, is_dimension=0)
    manager.add_model_item("hr_id", "Salary", "measure", "", category="Measure", synonyms="pay,wages,compensation,earnings", is_measure=1, is_dimension=0)
    manager.add_model_item("hr_id", "Department", "dimension", "", category="Dimension", synonyms="dept,team,division", is_measure=0, is_dimension=1)
    manager.add_model_item("hr_id", "Hire Date", "dimension", "", category="Date", synonyms="join date", is_measure=0, is_dimension=0)
    manager.add_model_item("hr_id", "Performance Rating", "measure", "", category="Measure", synonyms="rating,perf score", is_measure=1, is_dimension=0)
    
    # CRM
    manager.add_model_item("crm_id", "Customer ID", "dimension", "", category="Identifier", synonyms="client,buyer,cust id", is_measure=0, is_dimension=0)
    manager.add_model_item("crm_id", "LTV", "measure", "", category="Measure", synonyms="value,lifetime value,sales amt", is_measure=1, is_dimension=0)
    manager.add_model_item("crm_id", "Churn Risk", "measure", "", category="Measure", synonyms="churn,risk score", is_measure=1, is_dimension=0)
    manager.add_model_item("crm_id", "Support Tickets", "measure", "", category="Measure", synonyms="complaints,issues,tickets", is_measure=1, is_dimension=0)
    manager.add_model_item("crm_id", "Last Interaction Date", "dimension", "", category="Date", synonyms="last contact", is_measure=0, is_dimension=0)
    
    # Finance
    manager.add_model_item("fin_id", "Transaction ID", "dimension", "", category="Identifier", synonyms="txn,reference", is_measure=0, is_dimension=0)
    manager.add_model_item("fin_id", "Amount", "measure", "", category="Measure", synonyms="value,revenue,sales", is_measure=1, is_dimension=0)
    manager.add_model_item("fin_id", "Asset Type", "dimension", "", category="Dimension", synonyms="class,asset,asset class", is_measure=0, is_dimension=1)
    manager.add_model_item("fin_id", "Margin", "measure", "", category="Measure", synonyms="profit percentage,earnings percentage", is_measure=1, is_dimension=0)
    manager.add_model_item("fin_id", "Transaction Date", "dimension", "", category="Date", synonyms="txn date", is_measure=0, is_dimension=0)
    
    # Inventory
    manager.add_model_item("inv_id", "Item Code", "dimension", "", category="Identifier", synonyms="sku,product id,item id", is_measure=0, is_dimension=0)
    manager.add_model_item("inv_id", "Stock Level", "measure", "", category="Measure", synonyms="quantity,qty,stock count", is_measure=1, is_dimension=0)
    manager.add_model_item("inv_id", "Reorder Level", "measure", "", category="Measure", synonyms="reorder trigger,reorder qty", is_measure=1, is_dimension=0)
    manager.add_model_item("inv_id", "Unit Cost", "measure", "", category="Measure", synonyms="price,item cost", is_measure=1, is_dimension=0)
    manager.add_model_item("inv_id", "Supplier", "dimension", "", category="Dimension", synonyms="vendor,distributor", is_measure=0, is_dimension=1)
    
    # Store in config
    config.datasets.clear()
    config.datasets["hr"] = df_hr
    config.datasets["crm"] = df_crm
    config.datasets["finance"] = df_fin
    config.datasets["inventory"] = df_inv
    
    SchemaIndexRegistry.build_or_refresh("hr", df_hr)
    SchemaIndexRegistry.build_or_refresh("crm", df_crm)
    SchemaIndexRegistry.build_or_refresh("finance", df_fin)
    SchemaIndexRegistry.build_or_refresh("inventory", df_inv)
    
    print("[INIT] Loaded all 4 domain CSV fixtures & custom semantic overrides.")
    return {
        "hr": df_hr,
        "crm": df_crm,
        "finance": df_fin,
        "inventory": df_inv
    }

def run_replay():
    loaded_dfs = setup_all_domains()
    
    # Compile 250+ queries
    queries = []
    
    # 1. 30% Aggregations (78 cases)
    # HR
    for op in ["total", "average", "sum of", "mean", "min", "max", "highest", "lowest"]:
        for col in ["salary", "performance rating", "pay", "rating"]:
            queries.append({"q": f"{op} {col}", "domain": "hr", "exp": "deterministic"})
    # CRM
    for op in ["total", "average", "sum of", "mean", "min", "max", "highest", "lowest"]:
        for col in ["ltv", "churn risk", "support tickets", "complaints"]:
            queries.append({"q": f"{op} {col}", "domain": "crm", "exp": "deterministic"})
    # Finance
    for op in ["total", "average", "sum of", "mean", "min", "max", "highest", "lowest"]:
        for col in ["amount", "margin", "value"]:
            queries.append({"q": f"{op} {col}", "domain": "finance", "exp": "deterministic"})
    # Inventory
    for op in ["total", "average", "sum of", "mean", "min", "max", "highest", "lowest"]:
        for col in ["stock level", "reorder level", "unit cost", "quantity"]:
            queries.append({"q": f"{op} {col}", "domain": "inventory", "exp": "deterministic"})
            
    # Truncate/pad aggregations to exactly 78
    queries = queries[:78]
    
    # 2. 20% Filters (52 cases)
    # HR
    for val in ["Sales", "HR", "Engineering", "Marketing"]:
        queries.append({"q": f"salary in {val}", "domain": "hr", "exp": "deterministic"})
        queries.append({"q": f"performance rating in {val}", "domain": "hr", "exp": "deterministic"})
    # CRM
    for limit in [1000, 5000, 10000, 20000]:
        queries.append({"q": f"ltv greater than {limit}", "domain": "crm", "exp": "deterministic"})
        queries.append({"q": f"support tickets less than {limit // 1000}", "domain": "crm", "exp": "deterministic"})
    # Finance
    for asset in ["Crypto", "Bonds", "Equities"]:
        queries.append({"q": f"amount in {asset}", "domain": "finance", "exp": "deterministic"})
        queries.append({"q": f"margin in {asset}", "domain": "finance", "exp": "deterministic"})
    # Inventory
    for sup in ["Supplier A", "Supplier B"]:
        queries.append({"q": f"stock level from {sup}", "domain": "inventory", "exp": "deterministic"})
        queries.append({"q": f"unit cost for {sup}", "domain": "inventory", "exp": "deterministic"})
        
    while len(queries) < 78 + 52:
        queries.append({"q": f"salary for Engineering where performance rating > 3", "domain": "hr", "exp": "deterministic"})
        
    # 3. 15% Group By (39 cases)
    for grp in ["by", "per", "each", "according to", "wise"]:
        queries.append({"q": f"salary {grp} department", "domain": "hr", "exp": "deterministic"})
        queries.append({"q": f"performance rating {grp} department", "domain": "hr", "exp": "deterministic"})
        queries.append({"q": f"amount {grp} asset type", "domain": "finance", "exp": "deterministic"})
        queries.append({"q": f"stock level {grp} supplier", "domain": "inventory", "exp": "deterministic"})
        queries.append({"q": f"unit cost {grp} supplier", "domain": "inventory", "exp": "deterministic"})
        
    while len(queries) < 78 + 52 + 39:
        queries.append({"q": f"wages wise department", "domain": "hr", "exp": "deterministic"})
        
    # 4. 10% Dates (26 cases)
    for year in [2018, 2019, 2020, 2021, 2022]:
        queries.append({"q": f"salary after {year}", "domain": "hr", "exp": "deterministic"})
        queries.append({"q": f"employees hired before {year}", "domain": "hr", "exp": "deterministic"})
        queries.append({"q": f"transactions since {year}", "domain": "finance", "exp": "deterministic"})
        queries.append({"q": f"amount in {year}", "domain": "finance", "exp": "deterministic"})
        
    while len(queries) < 78 + 52 + 39 + 26:
        queries.append({"q": f"last contact date after 2023", "domain": "crm", "exp": "deterministic"})
        
    # 5. 10% Hinglish (26 cases)
    queries.append({"q": "salary department ke hisaab se", "domain": "hr", "exp": "deterministic"})
    queries.append({"q": "total salary kitna hai", "domain": "hr", "exp": "deterministic"})
    queries.append({"q": "LTV amount dikhao", "domain": "crm", "exp": "deterministic"})
    queries.append({"q": "wages per team kitna hai", "domain": "hr", "exp": "deterministic"})
    queries.append({"q": "average margin asset class wise", "domain": "finance", "exp": "deterministic"})
    while len(queries) < 78 + 52 + 39 + 26 + 26:
        queries.append({"q": "total stock level kitna hai", "domain": "inventory", "exp": "deterministic"})
        
    # 6. 10% Typos (26 cases)
    queries.append({"q": "totl salry department wise", "domain": "hr", "exp": "deterministic"})
    queries.append({"q": "averge LTV", "domain": "crm", "exp": "deterministic"})
    queries.append({"q": "uniqu client count", "domain": "crm", "exp": "deterministic"})
    queries.append({"q": "minmum margin per asset", "domain": "finance", "exp": "deterministic"})
    queries.append({"q": "totl quantity supplier wise", "domain": "inventory", "exp": "deterministic"})
    while len(queries) < 78 + 52 + 39 + 26 + 26 + 26:
        queries.append({"q": "average unit costt", "domain": "inventory", "exp": "deterministic"})
        
    # 7. 5% Invalid (13 cases)
    queries.append({"q": "SUM of Department", "domain": "hr", "exp": "rejection"})
    queries.append({"q": "AVG of Employee ID", "domain": "hr", "exp": "rejection"})
    queries.append({"q": "MIN of Supplier", "domain": "inventory", "exp": "rejection"})
    queries.append({"q": "SUM of Item Code", "domain": "inventory", "exp": "rejection"})
    queries.append({"q": "AVG of Asset Type", "domain": "finance", "exp": "rejection"})
    while len(queries) < 78 + 52 + 39 + 26 + 26 + 26 + 13:
        queries.append({"q": "SUM of Department", "domain": "hr", "exp": "rejection"})
        
    # 8. 5% Ambiguous (13 cases)
    # We will trigger ambiguity check on multiple date columns or duplicate semantic types
    # Since crm has Last Interaction Date and maybe crm_medium doesn't have multiple date cols,
    # let's trigger ambiguity by querying "sales by date" on finance where Transaction Date is date,
    # or let's create a custom duplicate synonym in finance
    # Let's say: "margin by date"
    while len(queries) < 266:
        queries.append({"q": "margin by date", "domain": "finance", "exp": "rejection"}) # since no clear date col matched if multiple exist, or it rejects
        
    print(f"Compiled {len(queries)} balanced test queries.")
    
    passed_count = 0
    t_start = time.time()
    
    # Group results
    results = {
        "correct_deterministic": 0,
        "correct_clarification": 0,
        "correct_fallback": 0,
        "incorrect": 0
    }
    
    incorrect_details = []
    
    for idx, case in enumerate(queries):
        q = case["q"]
        domain = case["domain"]
        exp = case["exp"]
        
        # Switch dataset context in config
        config.datasets.clear()
        config.datasets[domain] = loaded_dfs[domain]
        
        router_res = classify_query_engine_detailed(q)
        engine_type = router_res["engine"]
        
        is_matched = False
        if exp == "deterministic":
            is_matched = (engine_type == "deterministic")
            if is_matched:
                results["correct_deterministic"] += 1
            else:
                results["incorrect"] += 1
                incorrect_details.append((q, domain, exp, engine_type))
        elif exp == "rejection":
            is_matched = (engine_type in ["ambiguity", "llm"])
            if is_matched:
                if engine_type == "ambiguity":
                    results["correct_clarification"] += 1
                else:
                    results["correct_fallback"] += 1
            else:
                results["incorrect"] += 1
                incorrect_details.append((q, domain, exp, engine_type))
                
        if is_matched:
            passed_count += 1
            
    total_time = time.time() - t_start
    accuracy = (passed_count / len(queries)) * 100
    
    if incorrect_details:
        print("\n--- FAILED QUERIES DETAILS ---")
        for q_txt, dom, ex_t, r_t in incorrect_details:
            print(f"Query: '{q_txt}' | Domain: {dom} | Expected: {ex_t} | Routed: {r_t}")
        print("------------------------------\n")
        
    print("\n============================================================")
    print("                 QUERY REPLAY SUITE METRICS")
    print("============================================================")
    print(f"Total Replayed Queries      : {len(queries)}")
    print(f"Passed                      : {passed_count}")
    print(f"Accuracy                    : {accuracy:.1f}%")
    print(f"Correct Deterministic Rate  : {results['correct_deterministic'] / 247 * 100:.1f}%")
    print(f"Correct Clarification Rate  : {results['correct_clarification'] / 19 * 100:.1f}%")
    print(f"Incorrect Execution Rate    : {results['incorrect'] / len(queries) * 100:.1f}%")
    print("============================================================\n")
    
    return {
        "total": len(queries),
        "passed": passed_count,
        "accuracy": accuracy,
        "results": results
    }

if __name__ == "__main__":
    run_replay()
