from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import uuid
import backend.services.history_db as db
from backend.services.security_manager import verify_token

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

class WorkspaceCreate(BaseModel):
    name: str

@router.get("")
def list_workspaces(user: dict = Depends(verify_token)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Super Admin/Admin can see all workspaces, others see workspaces where they are members
    if user.get("role") in ["Super Admin", "Admin"]:
        cursor.execute("SELECT * FROM workspaces ORDER BY created_at DESC")
    else:
        cursor.execute(
            """
            SELECT w.* FROM workspaces w
            JOIN workspace_members m ON w.id = m.workspace_id
            WHERE m.user_id = ?
            ORDER BY w.created_at DESC
            """,
            (user.get("user_id"),)
        )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.post("/create")
def create_workspace(payload: WorkspaceCreate, user: dict = Depends(verify_token)):
    # Verify permission to create workspaces
    if user.get("role") not in ["Super Admin", "Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Access Denied: Cannot create workspaces")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Check duplicate
    cursor.execute("SELECT id FROM workspaces WHERE name = ?", (payload.name,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Workspace name already exists")
        
    workspace_id = str(uuid.uuid4())
    cursor.execute("INSERT INTO workspaces (id, name) VALUES (?, ?)", (workspace_id, payload.name))
    
    # Auto-add creator as workspace member
    cursor.execute(
        "INSERT INTO workspace_members (id, workspace_id, user_id, role) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), workspace_id, user.get("user_id"), user.get("role"))
    )
    conn.commit()
    conn.close()

    # Audit Log
    from backend.services.security import log_audit_action
    log_audit_action(user.get("username"), "Create Workspace", f"Created workspace: {payload.name}")

    return {"status": "success", "workspace_id": workspace_id, "name": payload.name}
