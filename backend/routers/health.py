"""
backend/routers/health.py
──────────────────────────
Health endpoints for subsystem status monitoring.

  GET /api/health         — full system health snapshot
  GET /api/datasets/health/{id} — per-dataset quality metrics
"""
from fastapi import APIRouter, HTTPException
import backend.config as config

router = APIRouter(prefix="/api")


@router.get("/health")
def get_system_health():
    """
    Returns real-time health status for all backend subsystems.

    Cached for 30 seconds to avoid hammering Ollama on every poll.
    Response shape:
    {
      "backend": "ok",
      "version": "2.0.0",
      "uptime_seconds": 3600,
      "dataset": "loaded" | "not_loaded",
      "dataset_count": 1,
      "dataset_names": ["Sales Report"],
      "llm": "connected" | "unreachable",
      "model": "qwen2.5:7b",
      "model_available": true,
      "cache": "ok" | "error",
      "prompt_files": "ok" | "warn"
    }
    """
    try:
        from backend.services.startup_validator import get_system_health
        return get_system_health()
    except Exception as e:
        # Fallback: return a minimal health response even if validator fails
        return {
            "backend": "ok",
            "version": config.app_settings.app_version,
            "dataset": "loaded" if config.datasets else "not_loaded",
            "llm": "unknown",
            "model": config.settings.get("model", config.app_settings.default_model),
            "cache": "unknown",
            "error": str(e),
        }


@router.get("/live")
def get_liveness():
    """
    Lightweight liveness probe to verify FastAPI process is running.
    """
    return {"status": "alive", "timestamp": config.datetime.now().isoformat() if hasattr(config, 'datetime') else None}


@router.get("/ready")
def get_readiness():
    """
    Readiness probe to verify database and registry services are healthy.
    """
    try:
        import backend.services.history_db as db
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection unhealthy: {e}")


@router.get("/datasets/health/{id}")
def get_dataset_health(id: str):
    """
    Returns per-dataset quality metrics including missing values,
    duplicates, outliers, skewness, and recommended fixes.
    """
    try:
        import backend.services.history_db as db
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM datasets WHERE id = ? LIMIT 1", (id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            # Fallback to active dataset if id not found
            active_dataset_name = None
            for name in config.datasets.keys():
                active_dataset_name = name
                break
            if active_dataset_name:
                dataset_name = active_dataset_name
            else:
                raise HTTPException(status_code=404, detail="No active datasets loaded.")
        else:
            dataset_name = row["name"]

        from backend.services.health import DatasetHealthService
        service = DatasetHealthService()
        return service.calculate_health(dataset_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
