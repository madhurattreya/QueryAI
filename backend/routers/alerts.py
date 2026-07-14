from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.alert_engine import AlertEngine

router = APIRouter(prefix="/api")

class RegisterAlertRequest(BaseModel):
    dataset_id: str
    metric_column: str
    condition: str  # ">", "<", "=="
    threshold_value: float
    email_recipient: str

@router.get("/alerts")
def get_alerts_endpoint(dataset_id: str = None):
    try:
        service = AlertEngine()
        return service.list_alerts(dataset_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/alerts")
def register_alert_endpoint(req: RegisterAlertRequest):
    try:
        service = AlertEngine()
        alert_id = service.register_alert(
            req.dataset_id,
            req.metric_column,
            req.condition,
            req.threshold_value,
            req.email_recipient
        )
        return {"status": "success", "id": alert_id, "message": "Alert registered."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/alerts/{id}")
def delete_alert_endpoint(id: str):
    try:
        service = AlertEngine()
        service.delete_alert(id)
        return {"status": "success", "message": "Alert deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
