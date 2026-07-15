from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import hashlib
import uuid
import backend.services.history_db as db
from backend.services.security_manager import verify_token

router = APIRouter(prefix="/api/developer", tags=["developer"])

class APIKeyCreate(BaseModel):
    permissions: str
    workspace_id: str

@router.get("/keys")
def list_api_keys(user: dict = Depends(verify_token)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, permissions, workspace_id, created_at FROM api_keys WHERE username = ?", (user.get("username"),))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.post("/keys")
def generate_api_key(payload: APIKeyCreate, user: dict = Depends(verify_token)):
    raw_key = f"qiq_{uuid.uuid4().hex}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    key_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO api_keys (id, key_hash, username, permissions, workspace_id) VALUES (?, ?, ?, ?, ?)",
        (key_id, key_hash, user.get("username"), payload.permissions, payload.workspace_id)
    )
    conn.commit()
    conn.close()

    # Audit Log
    from backend.services.security import log_audit_action
    log_audit_action(user.get("username"), "Generate API Key", f"Generated key with ID {key_id}")

    return {
        "status": "success",
        "key_id": key_id,
        "api_key": raw_key,
        "note": "Save this key now. It will not be shown again."
    }

@router.delete("/keys/{id}")
def revoke_api_key(id: str, user: dict = Depends(verify_token)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE id = ? AND username = ?", (id, user.get("username")))
    conn.commit()
    conn.close()

    # Audit Log
    from backend.services.security import log_audit_action
    log_audit_action(user.get("username"), "Revoke API Key", f"Revoked API key: {id}")

    return {"status": "success", "message": "API key revoked"}
