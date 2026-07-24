import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Request
from backend.services.dataset_manager import DatasetManager
from backend.models.schemas import FolderImportRequest

router = APIRouter(prefix="/api")


MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
ALLOWED_MIME_TYPES = {
    "text/csv", 
    "application/csv",
    "text/comma-separated-values",
    "text/x-comma-separated-values",
    "application/x-csv",
    "text/plain",
    "application/vnd.ms-excel", 
    "application/vnd.msexcel",
    "application/excel",
    "application/x-excel",
    "application/x-msexcel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream"
}

@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    behavior: str = Query("keep", enum=["keep", "replace"])
):
    """
    Harden file upload validator. Saves file temporarily and registers it via DatasetManager.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV or Excel.")

    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid MIME type. Please upload valid CSV or Excel.")

    # Save to a temporary file to calculate hash & register safely
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"nexus_upload_{file.filename}")
    
    total_size = 0
    try:
        with open(temp_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    f.close()
                    raise HTTPException(status_code=413, detail="File size exceeds maximum limit of 25MB.")
                f.write(chunk)
                
        # Extract user_id from Authorization token
        user_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                from backend.services.security_manager import decode_jwt
                payload = decode_jwt(token)
                user_id = payload.get("user_id") or payload.get("username") or payload.get("sub")
            except Exception:
                pass

        # Register via DatasetManager
        manager = DatasetManager()
        reg_result = manager.register_dataset_file(
            original_filename=file.filename,
            source_path=temp_path,
            behavior=behavior,
            user_id=user_id
        )
        
        workspace_id = request.headers.get("x-workspace-id")
        if workspace_id and reg_result.get("status") == "success":
            import backend.services.history_db as db
            ds_id = reg_result.get("id")
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE datasets SET workspace_id = ? WHERE id = ?", (workspace_id, ds_id))
            conn.commit()
            conn.close()

        return reg_result
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temporary upload file
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except Exception: pass

@router.post("/upload/folder")
def import_folder(req: FolderImportRequest, request: Request):
    """
    Scans a local directory on server/host disk and batch-registers all supported data files (.csv, .xlsx, .xls, .parquet, .json).
    """
    from backend.models.schemas import FolderImportRequest
    folder_path = req.folder_path.strip().strip('"').strip("'")
    
    if not os.path.exists(folder_path):
        raise HTTPException(status_code=404, detail=f"Directory path '{folder_path}' does not exist on disk.")
        
    if not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail=f"Path '{folder_path}' is a file, not a directory.")
        
    # Extract user_id
    user_id = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            from backend.services.security_manager import decode_jwt
            payload = decode_jwt(token)
            user_id = payload.get("user_id") or payload.get("username") or payload.get("sub")
        except Exception:
            pass

    manager = DatasetManager()
    registered_files = []
    failed_files = []
    
    supported_exts = {".csv", ".xlsx", ".xls", ".parquet", ".json"}
    
    for root, _, files in os.walk(folder_path):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in supported_exts and not fname.startswith("~$") and not fname.startswith("."):
                full_file_path = os.path.join(root, fname)
                try:
                    res = manager.register_dataset_file(
                        original_filename=fname,
                        source_path=full_file_path,
                        behavior=req.behavior,
                        user_id=user_id
                    )
                    if res.get("status") == "success":
                        registered_files.append({"filename": fname, "id": res.get("id"), "rows": res.get("rows")})
                    else:
                        failed_files.append({"filename": fname, "reason": res.get("message")})
                except Exception as ex:
                    failed_files.append({"filename": fname, "reason": str(ex)})

    if not registered_files and not failed_files:
        raise HTTPException(status_code=400, detail=f"No supported data files (.csv, .xlsx, .parquet, .json) found in folder '{folder_path}'.")

    return {
        "status": "success",
        "message": f"Successfully registered {len(registered_files)} dataset(s) from directory.",
        "registered_count": len(registered_files),
        "failed_count": len(failed_files),
        "registered_files": registered_files,
        "failed_files": failed_files
    }

