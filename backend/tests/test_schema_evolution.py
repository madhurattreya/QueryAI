import sys
import os
import uuid
import pandas as pd
from datetime import datetime

# Adjust sys path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.config as config
from backend.services.query_parser import parse_question, get_semantic_layer
from backend.services.schema_index import SchemaIndexRegistry, SemanticType
from backend.services.semantic_model import SemanticModelManager
from backend.services.metric_catalog import MetricCatalog
import backend.services.history_db as db

def test_schema_evolution():
    print("============================================================")
    print("               TESTING SCHEMA EVOLUTION GATE")
    print("============================================================")
    
    # 1. Setup Initial DataFrame
    df = pd.DataFrame({
        "Customer ID": ["C1", "C2", "C3"],
        "LTV": [1000.0, 1500.0, 2000.0],
        "Churn Risk": [0, 1, 0]
    })
    
    dataset_name = "CRM_Evolution"
    dataset_id = str(uuid.uuid4())
    
    # Init DB
    db.init_db()
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Clear existing
    cursor.execute("DELETE FROM datasets WHERE name = ?", (dataset_name,))
    cursor.execute("DELETE FROM semantic_model WHERE dataset_id IN (SELECT id FROM datasets WHERE name = ?)", (dataset_name,))
    
    # Insert new record
    cursor.execute(
        """
        INSERT INTO datasets (id, name, filename, hash, rows, columns, is_active, status, upload_time)
        VALUES (?, ?, ?, ?, ?, ?, 1, 'active', ?)
        """,
        (dataset_id, dataset_name, "crm_evolution.csv", "hash_crm_evo", len(df), len(df.columns), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    # 2. Add Initial Semantic Overrides
    manager = SemanticModelManager()
    manager.add_model_item(dataset_id, "Customer ID", "dimension", "", category="Identifier", synonyms="customer,buyer,client", is_measure=0, is_dimension=0)
    manager.add_model_item(dataset_id, "LTV", "measure", "", category="Measure", synonyms="value,ltv amount", is_measure=1, is_dimension=0)
    
    # Load into config datasets
    config.datasets[dataset_name] = df
    SchemaIndexRegistry.build_or_refresh(dataset_name, df)
    
    # Warm up metric catalog
    schema_index = SchemaIndexRegistry.get(dataset_name)
    catalog = MetricCatalog(schema_index)
    
    # Parse initial query
    parsed = parse_question("total ltv", df, dataset_name)
    print(f"[STAGE 1] 'total ltv' parsed column: {parsed.execution_plan.get('aggregations')}")
    assert len(parsed.execution_plan.get("aggregations", [])) > 0, "LTV sum aggregation should be detected"
    assert parsed.execution_plan["aggregations"][0]["column"] == "LTV", "Target column should be LTV"
    assert parsed.confidence > 0.8, "Initial parse confidence should be high"
    
    # 3. Dynamic Schema Rename (Customer ID -> Customer Number, LTV -> LTV Amount)
    df_evolved = df.rename(columns={
        "Customer ID": "Customer Number",
        "LTV": "LTV Amount"
    })
    
    # Update SQLite database semantic entries
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM semantic_model WHERE dataset_id = ?", (dataset_id,))
    conn.commit()
    conn.close()
    
    # Register evolved column mappings in DB
    manager.add_model_item(dataset_id, "Customer Number", "dimension", "", category="Identifier", synonyms="customer,buyer,client", is_measure=0, is_dimension=0)
    manager.add_model_item(dataset_id, "LTV Amount", "measure", "", category="Measure", synonyms="value,ltv amount", is_measure=1, is_dimension=0)
    
    # Rebuild index and config datasets
    config.datasets[dataset_name] = df_evolved
    SchemaIndexRegistry.build_or_refresh(dataset_name, df_evolved)
    
    # 4. Assert Adaptation to Schema Evolution
    parsed_new = parse_question("total ltv", df_evolved, dataset_name)
    print(f"[STAGE 2] 'total ltv' parsed evolved column: {parsed_new.execution_plan.get('aggregations')}")
    assert len(parsed_new.execution_plan.get("aggregations", [])) > 0, "Evolved LTV sum aggregation should be detected"
    assert parsed_new.execution_plan["aggregations"][0]["column"] == "LTV Amount", "Target column should dynamically adapt to 'LTV Amount'"
    
    # Test query targeting old column directly (which doesn't exist now)
    parsed_old_col = parse_question("average employee id", df_evolved, dataset_name)
    print(f"[STAGE 3] Query targeting obsolete column 'employee id' confidence: {parsed_old_col.confidence}")
    assert parsed_old_col.confidence < 0.75 or parsed_old_col.intent == "fallback", "Obsolete column should trigger fallback or rejection"
    
    print("Schema Evolution Gate: PASSED SUCCESSFULLY!")
    print("============================================================\n")

if __name__ == "__main__":
    test_schema_evolution()
