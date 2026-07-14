from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.relationship_engine import RelationshipEngine
import backend.services.history_db as db

router = APIRouter(prefix="/api")

class CreateRelationshipRequest(BaseModel):
    source_dataset_id: str
    source_column: str
    target_dataset_id: str
    target_column: str
    relationship_type: str

@router.get("/relationships")
def list_relationships():
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM relationships")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@router.get("/relationships/graph")
def get_relationship_graph_endpoint():
    try:
        engine = RelationshipEngine()
        return {"status": "success", "graph": engine.get_relationship_graph()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/relationships/discover")
def discover_relationships_endpoint():
    try:
        engine = RelationshipEngine()
        engine.discover_and_persist_relationships()
        return {"status": "success", "message": "Discovery scanning completed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/relationships")
def add_user_relationship(req: CreateRelationshipRequest):
    try:
        engine = RelationshipEngine()
        rel_id = engine.add_user_defined_relationship(
            req.source_dataset_id,
            req.source_column,
            req.target_dataset_id,
            req.target_column,
            req.relationship_type
        )
        return {"status": "success", "id": rel_id, "message": "Manual relationship added."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/relationships/{id}")
def delete_relationship_endpoint(id: str):
    try:
        engine = RelationshipEngine()
        engine.delete_relationship(id)
        return {"status": "success", "message": "Relationship removed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
