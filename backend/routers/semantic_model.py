from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.semantic_model import SemanticModelManager

router = APIRouter(prefix="/api")

class SemanticItemRequest(BaseModel):
    dataset_id: str
    name: str
    type: str # "measure", "dimension", "hierarchy", "calculated_column", "calculated_measure"
    expression: str
    definition: str = ""

@router.get("/semantic-model")
def list_semantic_items(dataset_id: str = None):
    try:
        manager = SemanticModelManager()
        return manager.get_model_items(dataset_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/semantic-model")
def add_semantic_item(req: SemanticItemRequest):
    try:
        manager = SemanticModelManager()
        item_id = manager.add_model_item(
            req.dataset_id,
            req.name,
            req.type,
            req.expression,
            req.definition
        )
        return {"status": "success", "id": item_id, "message": "Semantic item created."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/semantic-model/{id}")
def delete_semantic_item(id: str):
    try:
        manager = SemanticModelManager()
        manager.delete_model_item(id)
        return {"status": "success", "message": "Semantic item deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/semantic-model/hierarchies/{dataset_id}")
def get_hierarchies_endpoint(dataset_id: str):
    try:
        manager = SemanticModelManager()
        return manager.get_hierarchies(dataset_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
