from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.dashboard_manager import DashboardManager

router = APIRouter(prefix="/api")

class CreateDashboardRequest(BaseModel):
    title: str
    layout: dict = None

class UpdateDashboardRequest(BaseModel):
    title: str = None
    layout: dict = None

@router.get("/dashboards")
def list_dashboards_endpoint():
    try:
        manager = DashboardManager()
        return manager.list_dashboards()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboards/live_metrics")
def get_live_dashboard_metrics():
    try:
        from backend.services.ai_dashboard import AIDashboardService
        service = AIDashboardService()
        return service.compute_live_dashboard_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/dashboards/{id}")
def get_dashboard_endpoint(id: str):
    try:
        manager = DashboardManager()
        dash = manager.get_dashboard(id)
        if not dash:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return dash
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dashboards")
def create_dashboard_endpoint(req: CreateDashboardRequest):
    try:
        manager = DashboardManager()
        dash_id = manager.create_dashboard(req.title, req.layout)
        return {"status": "success", "id": dash_id, "message": "Dashboard created."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class AIGenerateRequest(BaseModel):
    question: str
    schema_desc: str = ""

class AIEditRequest(BaseModel):
    question: str

@router.post("/dashboards/ai/generate")
def ai_generate_dashboard_endpoint(req: AIGenerateRequest):
    try:
        from backend.services.ai_dashboard import AIDashboardService
        service = AIDashboardService()
        return service.generate_dashboard(req.question, req.schema_desc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dashboards/ai/edit/{id}")
def ai_edit_dashboard_endpoint(id: str, req: AIEditRequest):
    try:
        from backend.services.ai_dashboard import AIDashboardService
        service = AIDashboardService()
        return service.edit_dashboard(id, req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/dashboards/{id}")
def update_dashboard_endpoint(id: str, req: UpdateDashboardRequest):
    try:
        manager = DashboardManager()
        manager.update_dashboard(id, req.title, req.layout)
        return {"status": "success", "message": "Dashboard updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/dashboards/{id}")
def delete_dashboard_endpoint(id: str):
    try:
        manager = DashboardManager()
        manager.delete_dashboard(id)
        return {"status": "success", "message": "Dashboard deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
