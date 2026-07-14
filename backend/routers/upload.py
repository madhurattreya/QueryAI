import os
import tempfile
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from backend.services.dataset_manager import DatasetManager

router = APIRouter(prefix="/api")

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
ALLOWED_MIME_TYPES = {
    "text/csv", 
    "application/vnd.ms-excel", 
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
}

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    behavior: str = Query("keep", enum=["keep", "replace"])
):
    """
    Harden file upload validator. Saves file temporarily and registers it via DatasetManager.
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV or Excel.")

    if file.content_type not in ALLOWED_MIME_TYPES:
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
                
        # Register via DatasetManager
        manager = DatasetManager()
        reg_result = manager.register_dataset_file(
            original_filename=file.filename,
            source_path=temp_path,
            behavior=behavior
        )
        
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
