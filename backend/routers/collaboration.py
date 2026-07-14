from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.collaboration import CollaborationService

router = APIRouter(prefix="/api")

class CommentRequest(BaseModel):
    dashboard_id: str
    username: str
    comment: str

class FavoriteRequest(BaseModel):
    username: str
    query: str
    title: str

@router.get("/collaboration/comments/{dashboard_id}")
def get_comments_endpoint(dashboard_id: str):
    try:
        service = CollaborationService()
        return service.get_comments(dashboard_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collaboration/comments")
def add_comment_endpoint(req: CommentRequest):
    try:
        service = CollaborationService()
        comment_id = service.add_comment(req.dashboard_id, req.username, req.comment)
        return {"status": "success", "id": comment_id, "message": "Comment added."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collaboration/favorites")
def get_favorites_endpoint(username: str = None):
    try:
        service = CollaborationService()
        return service.get_favorites(username)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collaboration/favorites")
def add_favorite_endpoint(req: FavoriteRequest):
    try:
        service = CollaborationService()
        fav_id = service.add_favorite(req.username, req.query, req.title)
        return {"status": "success", "id": fav_id, "message": "Query bookmarked as favorite."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/collaboration/favorites/{id}")
def delete_favorite_endpoint(id: str):
    try:
        service = CollaborationService()
        service.delete_favorite(id)
        return {"status": "success", "message": "Favorite bookmark removed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
