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
    Returns metadata and stats of all registered datasets.
    """
    workspace_id = request.headers.get("x-workspace-id")
    conn = db.get_db_connection()
    cursor = conn.cursor()
    if workspace_id:
        cursor.execute("SELECT * FROM datasets WHERE workspace_id = ? ORDER BY upload_time DESC", (workspace_id,))
    else:
        cursor.execute("SELECT * FROM datasets ORDER BY upload_time DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@router.post("/datasets/active")
def set_active_dataset_endpoint(req: ActivateRequest):
    """
    Thread-safe activation switcher.
    """
    try:
        manager = DatasetManager()
        manager.activate_dataset_by_id(req.id)
        return {"status": "success", "message": f"Activated dataset {req.id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/datasets/active/multiple")
def set_active_datasets_endpoint(req: ActivateMultipleRequest):
    """
    Thread-safe multi-activation switcher.
    """
    try:
        manager = DatasetManager()
        manager.activate_datasets_multiple(req.ids)
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
