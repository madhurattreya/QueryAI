from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.dataset_manager import DatasetManager
import backend.services.history_db as db

router = APIRouter(prefix="/api")

class ActivateRequest(BaseModel):
    id: str

class ActivateMultipleRequest(BaseModel):
    ids: list[str]

class RenameRequest(BaseModel):
    id: str
    name: str

from fastapi import Request

@router.get("/datasets")
def list_datasets_endpoint(request: Request):
    """
    Returns metadata and stats of all registered datasets for the authenticated user.
    """
    user_id = None
    user_role = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            from backend.services.security_manager import decode_jwt
            payload = decode_jwt(token)
            user_id = payload.get("user_id") or payload.get("username") or payload.get("sub")
            user_role = payload.get("role")
        except Exception:
            pass

    workspace_id = request.headers.get("x-workspace-id")
    conn = db.get_db_connection()
    cursor = conn.cursor()

    if user_id and user_role != "Super Admin":
        if workspace_id:
            cursor.execute("SELECT * FROM datasets WHERE (user_id = ? OR user_id IS NULL OR workspace_id = ? OR workspace_id IS NULL) ORDER BY upload_time DESC", (user_id, workspace_id))
        else:
            cursor.execute("SELECT * FROM datasets WHERE (user_id = ? OR user_id IS NULL) ORDER BY upload_time DESC", (user_id,))
    else:
        if workspace_id:
            cursor.execute("SELECT * FROM datasets WHERE (workspace_id = ? OR workspace_id IS NULL) ORDER BY upload_time DESC", (workspace_id,))
        else:
            cursor.execute("SELECT * FROM datasets ORDER BY upload_time DESC")

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@router.get("/datasets/active")
def get_active_dataset_endpoint():
    """
    Returns metadata of current active dataset.
    """
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM datasets WHERE is_active = 1 LIMIT 1")
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT * FROM datasets ORDER BY upload_time DESC LIMIT 1")
            row = cursor.fetchone()
        conn.close()

        if row:
            return {"status": "success", "dataset": dict(row)}

        if config.datasets:
            ds_name = list(config.datasets.keys())[0]
            df = config.datasets[ds_name]
            return {
                "status": "success",
                "dataset": {
                    "id": "active_file",
                    "name": ds_name,
                    "rows": len(df),
                    "columns": len(df.columns),
                    "columns_list": df.columns.tolist()
                }
            }
        return {"status": "none", "message": "No active dataset"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/datasets/active")
def set_active_dataset_endpoint(req: ActivateRequest, request: Request):
    """
    Thread-safe activation switcher.
    """
    user_id = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            from backend.services.security_manager import decode_jwt
            payload = decode_jwt(token)
            user_id = payload.get("user_id")
        except Exception:
            pass

    try:
        manager = DatasetManager()
        manager.activate_dataset_by_id(req.id, user_id=user_id)
        return {"status": "success", "message": f"Activated dataset {req.id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/datasets/active/multiple")
def set_active_datasets_endpoint(req: ActivateMultipleRequest, request: Request):
    """
    Thread-safe multi-activation switcher.
    """
    user_id = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            from backend.services.security_manager import decode_jwt
            payload = decode_jwt(token)
            user_id = payload.get("user_id")
        except Exception:
            pass

    try:
        manager = DatasetManager()
        manager.activate_datasets_multiple(req.ids, user_id=user_id)
        return {"status": "success", "message": f"Activated datasets {req.ids}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/datasets/rename")
def rename_dataset_endpoint(req: RenameRequest):
    try:
        manager = DatasetManager()
        manager.rename_dataset(req.id, req.name)
        return {"status": "success", "message": f"Dataset renamed to {req.name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/datasets/{id}")
def delete_dataset_endpoint(id: str):
    """
    Safely unloads and deletes a dataset.
    """
    try:
        manager = DatasetManager()
        manager.delete_dataset(id)
        return {"status": "success", "message": "Dataset deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/datasets")
def clear_all_datasets_endpoint():
    try:
        manager = DatasetManager()
        manager.clear_all_datasets()
        return {"status": "success", "message": "All datasets removed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/datasets/preview/{id}")
def get_dataset_preview_endpoint(id: str):
    try:
        manager = DatasetManager()
        preview = manager.get_dataset_preview(id)
        return {"status": "success", "result": preview}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/datasets/schema/{id}")
def get_dataset_schema_endpoint(id: str):
    try:
        manager = DatasetManager()
        # Preview first rows to map column types
        preview = manager.get_dataset_preview(id)
        if not preview:
            return {"status": "success", "columns": []}
            
        columns = []
        for col, val in preview[0].items():
            col_type = "string"
            if isinstance(val, (int, float)):
                col_type = "number"
            elif isinstance(val, bool):
                col_type = "boolean"
            columns.append({"name": col, "type": col_type})
            
        return {"status": "success", "columns": columns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
