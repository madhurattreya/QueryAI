from fastapi import APIRouter
from sqlalchemy import inspect
import backend.config as config
from backend.models.schemas import SettingsRequest
import backend.services.formatter as formatter

router = APIRouter(prefix="/api")

@router.get("/status")
def get_status():
    sources = list(config.datasets.keys()) if config.current_source_type == "file" else []
    tables = []
    if config.current_source_type == "sql" and config.database_engine:
        try:
            inspector = inspect(config.database_engine)
            tables = inspector.get_table_names()
        except Exception:
            pass
            
    return {
        "status": "Ready",
        "current_source_type": config.current_source_type,
        "loaded_files": list(config.datasets.keys()),
        "sql_connected": config.database_engine is not None,
        "db_flavor": config.db_flavor,
        "sql_tables": tables,
        "settings": config.settings,
        "has_gemini_key": config.GEMINI_API_KEY is not None
    }

@router.post("/settings")
def update_settings(req: SettingsRequest):
    config.settings["model"] = req.model
    config.settings["explain_mode"] = req.explain_mode
    config.settings["debug_mode"] = req.debug_mode
    config.settings["fast_mode"] = req.fast_mode
    
    # Sync settings with formatter flags
    formatter.explain_mode = req.explain_mode
    formatter.fast_mode = req.fast_mode
    formatter.debug_mode = req.debug_mode
    
    return {"status": "success", "settings": config.settings}
