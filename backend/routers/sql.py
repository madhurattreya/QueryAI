from fastapi import APIRouter, HTTPException
import os
import backend.config as config
from backend.models.schemas import SQLConnectionRequest, SwitchSourceRequest
from backend.services.dataset_manager import DatasetManager

router = APIRouter(prefix="/api")

@router.post("/connect-sql")
def connect_sql(req: SQLConnectionRequest):
    """
    Registers and encrypts database credentials using standard Fernet.
    """
    try:
        connection_params = {
            "sqlite_path": req.sqlite_path,
            "host": req.host,
            "port": req.port,
            "db_name": req.db_name,
            "username": req.username,
            "password": req.password
        }
        
        # Name connection
        conn_name = req.db_name if req.db_name else "sqlite_db"
        if req.sqlite_path:
            conn_name = os.path.splitext(os.path.basename(req.sqlite_path))[0]
            
        manager = DatasetManager()
        reg_result = manager.register_sql_connection(
            name=conn_name,
            db_type=req.db_type,
            connection_params=connection_params
        )
        
        return reg_result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/switch-source")
def switch_source(req: SwitchSourceRequest):
    """
    Switch source type manually.
    """
    if req.source_type not in ["file", "sql"]:
        raise HTTPException(status_code=400, detail="Invalid source type.")
    if req.source_type == "sql" and config.database_engine is None:
        raise HTTPException(status_code=400, detail="No SQL database is connected.")
    config.current_source_type = req.source_type
    return {"status": "success", "source_type": config.current_source_type}
