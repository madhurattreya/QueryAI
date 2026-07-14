from fastapi import APIRouter, HTTPException
from backend.services.search import EnterpriseSearchService

router = APIRouter(prefix="/api")

@router.get("/search")
def global_search_endpoint(q: str):
    if not q or not q.strip():
        return {"status": "success", "results": {"datasets": [], "semantic_model": [], "dashboards": [], "reports": [], "favorites": []}}
    try:
        service = EnterpriseSearchService()
        res = service.global_search(q)
        return {"status": "success", "results": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
