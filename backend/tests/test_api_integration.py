import sys
import os
import json
import pandas as pd
from datetime import datetime

# Adjust sys path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import backend.config as config
from backend.main import app
from backend.services.security_manager import verify_token
from backend.services.schema_index import SchemaIndexRegistry
import backend.services.history_db as db
import backend.services.kpi_engine as kpi_engine

from fastapi.testclient import TestClient

# 1. Override verify_token dependency for test runs
app.dependency_overrides[verify_token] = lambda: {"username": "test_developer", "role": "Admin"}

client = TestClient(app, base_url="http://localhost")

def test_api_integration_valid_query():
    print("============================================================")
    print("              RUNNING API E2E & SSE CONTRACT TEST")
    print("============================================================")
    
    # Setup Superstore dataset in config
    mock_df = pd.DataFrame({
        "Order ID": [1, 2, 3],
        "Customer ID": ["C1", "C2", "C3"],
        "Sales": [1000, 2000, 3000],
        "Profit": [100, 200, 300],
        "City": ["Delhi", "Mumbai", "Bangalore"]
    })
    
    # Initialize workspace DB
    db.init_db()
    
    # Clean up and insert test active dataset
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM datasets WHERE name = 'Superstore'")
    cursor.execute(
        """
        INSERT INTO datasets (id, name, filename, hash, rows, columns, is_active, status, upload_time)
        VALUES ('id_superstore', 'Superstore', 'superstore.csv', 'hash_superstore', 3, 5, 1, 'active', ?)
        """,
        (datetime.now().isoformat(),)
    )
    conn.commit()
    conn.close()
    
    config.datasets.clear()
    config.datasets["Superstore"] = mock_df
    config.current_source_type = "file"
    SchemaIndexRegistry.build_or_refresh("Superstore", mock_df)
    kpi_engine.compute_and_cache_kpis("Superstore", mock_df, "hash_superstore")
    
    # Post query request
    headers = {"x-workspace-id": "workspace_test"}
    req_body = {
        "question": "Total Sales",
        "conversation_id": "test_conv_id"
    }
    
    # Request E2E query stream
    response = client.post("/api/query", json=req_body, headers=headers)
    assert response.status_code == 200, "API endpoint should return HTTP 200"
    
    # Validate SSE response lines
    chunks = [line.strip() for line in response.iter_lines() if line.strip()]
    assert len(chunks) >= 2, "SSE stream should return multiple progress/result chunks"
    
    # Parse chunks
    progress_chunks = []
    final_payload = None
    
    for c in chunks:
        data = json.loads(c)
        if data.get("type") == "progress":
            progress_chunks.append(data)
        else:
            final_payload = data
            
    # 1. Assert chunk ordering (progress updates first)
    assert len(progress_chunks) > 0, "SSE stream must emit progress updates"
    assert final_payload is not None, "SSE stream must yield a final results payload"
    
    # 2. API Contract Freeze Checks (Asserting required fields & types)
    assert "status" in final_payload, "Contract Freeze: payload must contain 'status'"
    assert final_payload["status"] in ("success", "completed"), "Contract Freeze: payload status must indicate completion"
    
    assert "result" in final_payload, "Contract Freeze: payload must contain 'result'"
    assert isinstance(final_payload["result"], (list, dict, int, float)), "Contract Freeze: 'result' field must match types"
    
    assert "debug_info" in final_payload, "Contract Freeze: payload must contain 'debug_info'"
    debug = final_payload["debug_info"]
    assert isinstance(debug, dict), "Contract Freeze: 'debug_info' must be a dictionary"
    
    # Check OBS fields
    assert "confidence_score" in debug, "Contract Freeze: debug_info must contain 'confidence_score'"
    assert "engine_used" in debug, "Contract Freeze: debug_info must contain 'engine_used'"
    
    print("API SSE Contract Validation: PASSED!")
    print("============================================================\n")

if __name__ == "__main__":
    test_api_integration_valid_query()
