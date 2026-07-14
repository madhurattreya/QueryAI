from fastapi import APIRouter, HTTPException
import backend.services.history_db as db
from backend.services.security import check_permission

router = APIRouter(prefix="/api")

@router.get("/audit-logs")
def list_audit_logs():
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 500")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/security/permissions")
def get_permission_endpoint(role: str, action: str):
    is_allowed = check_permission(role, action)
    return {"status": "success", "role": role, "action": action, "allowed": is_allowed}
