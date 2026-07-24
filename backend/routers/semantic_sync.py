"""
backend/routers/semantic_sync.py
──────────────────────────────────
API Router for Enterprise Semantic Layer & dbt Sync operations.
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException, File, UploadFile, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
from backend.services.dbt_sync import dbt_sync_manager

router = APIRouter(prefix="/api/semantic", tags=["Semantic Sync"])

class DBTImportPayload(BaseModel):
    manifest_json: str

@router.post("/dbt-import")
async def import_dbt_manifest(payload: DBTImportPayload):
    """
    Import dbt manifest.json string and extract models, metrics, and relationships.
    """
    res = dbt_sync_manager.parse_dbt_manifest(payload.manifest_json)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "dbt import failed"))
    return res

@router.post("/dbt-upload")
async def upload_dbt_manifest_file(file: UploadFile = File(...)):
    """
    Upload a dbt manifest.json file directly.
    """
    try:
        content = await file.read()
        json_str = content.decode("utf-8")
        res = dbt_sync_manager.parse_dbt_manifest(json_str)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("error", "dbt manifest upload failed"))
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")
