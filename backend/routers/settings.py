from fastapi import APIRouter, Request
from sqlalchemy import inspect
import backend.config as config
import backend.services.history_db as db
from backend.models.schemas import SettingsRequest
import backend.services.formatter as formatter

router = APIRouter(prefix="/api")

@router.get("/status")
def get_status(request: Request):
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

    conn = db.get_db_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT name FROM datasets WHERE user_id = ? AND is_active = 1", (user_id,))
    else:
        cursor.execute("SELECT name FROM datasets WHERE is_active = 1")
    rows = cursor.fetchall()
    conn.close()

    loaded_files = [r["name"] for r in rows]

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
        "loaded_files": loaded_files,
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
    config.settings["technical_mode"] = req.technical_mode
    config.settings["explain_level"] = req.explain_level
    
    # Sync settings with formatter flags
    formatter.explain_mode = req.explain_mode
    formatter.fast_mode = req.fast_mode
    formatter.debug_mode = req.debug_mode
    formatter.technical_mode = req.technical_mode
    formatter.explain_level = req.explain_level
    
    return {"status": "success", "settings": config.settings}
