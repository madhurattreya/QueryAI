from fastapi import APIRouter, HTTPException
import backend.config as config

router = APIRouter(prefix="/api")

@router.get("/datasets/health/{id}")
def get_dataset_health(id: str):
    try:
        import backend.services.history_db as db
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM datasets WHERE id = ? LIMIT 1", (id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            # Fallback to active dataset if not found
            active_dataset_name = None
            for name, df in config.datasets.items():
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
