from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.scheduler import SchedulerService

router = APIRouter(prefix="/api")

class RegisterJobRequest(BaseModel):
    dashboard_id: str
    cron_expression: str
    export_format: str
    email_recipient: str

@router.get("/scheduler/jobs")
def get_jobs_endpoint():
    try:
        service = SchedulerService()
        return service.list_jobs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/scheduler/jobs")
def register_job_endpoint(req: RegisterJobRequest):
    try:
        service = SchedulerService()
        job_id = service.register_job(
            req.dashboard_id,
            req.cron_expression,
            req.export_format,
            req.email_recipient
        )
        return {"status": "success", "id": job_id, "message": "Scheduled job registered."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/scheduler/jobs/{id}")
def delete_job_endpoint(id: str):
    try:
        service = SchedulerService()
        service.delete_job(id)
        return {"status": "success", "message": "Scheduled job deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
