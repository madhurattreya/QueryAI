from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import json
import uuid
from datetime import datetime
import backend.services.history_db as db
from backend.services.security_manager import verify_token

router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])

class CommentCreate(BaseModel):
    username: str
    comment: str

class VersionCreate(BaseModel):
    author: str
    change_description: str
    status: str = "Draft"
    layout: dict

class FavoriteCreate(BaseModel):
    username: str
    query: str
    title: str

@router.get("/dashboards/{id}/comments")
def list_dashboard_comments(id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM comments WHERE dashboard_id = ? ORDER BY created_at DESC", (id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.post("/dashboards/{id}/comments")
def add_dashboard_comment(id: str, payload: CommentCreate, user: dict = Depends(verify_token)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    comment_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO comments (id, dashboard_id, username, comment) VALUES (?, ?, ?, ?)",
        (comment_id, id, payload.username, payload.comment)
    )
    conn.commit()
    conn.close()

    # Audit Log
    from backend.services.security import log_audit_action
    log_audit_action(payload.username, "Comment Added", f"Added comment on dashboard {id}")

    return {"status": "success", "comment_id": comment_id}


# Version Control Endpoints
@router.get("/dashboards/{id}/versions")
def list_dashboard_versions(id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM dashboard_versions WHERE dashboard_id = ? ORDER BY version_number DESC", (id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    # Deserialize layouts
    for r in rows:
        if r.get("layout"):
            try: r["layout"] = json.loads(r["layout"])
            except Exception: r["layout"] = {}
    return rows

@router.post("/dashboards/{id}/versions")
def save_dashboard_version(id: str, payload: VersionCreate, user: dict = Depends(verify_token)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Get current max version number
    cursor.execute("SELECT MAX(version_number) as max_v FROM dashboard_versions WHERE dashboard_id = ?", (id,))
    row = cursor.fetchone()
    next_v = (row["max_v"] or 0) + 1
    
    version_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO dashboard_versions (id, dashboard_id, version_number, author, change_description, status, layout)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (version_id, id, next_v, payload.author, payload.change_description, payload.status, json.dumps(payload.layout))
    )
    conn.commit()
    conn.close()

    # Audit Log
    from backend.services.security import log_audit_action
    log_audit_action(payload.author, "Dashboard Version Saved", f"Saved version {next_v} for dashboard {id}")

    return {"status": "success", "version_id": version_id, "version_number": next_v}

@router.post("/dashboards/{id}/versions/{version_number}/restore")
def restore_dashboard_version(id: str, version_number: int, user: dict = Depends(verify_token)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT layout FROM dashboard_versions WHERE dashboard_id = ? AND version_number = ?", (id, version_number))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Version not found")
        
    layout = row["layout"]
    cursor.execute("UPDATE dashboards SET layout = ?, updated_at = ? WHERE id = ?", (layout, datetime.now(), id))
    conn.commit()
    conn.close()

    # Audit Log
    from backend.services.security import log_audit_action
    log_audit_action(user.get("username"), "Dashboard Version Restored", f"Restored version {version_number} on dashboard {id}")

    return {"status": "success", "message": f"Restored version {version_number} successfully"}

@router.get("/dashboards/{id}/versions/compare")
def compare_dashboard_versions(id: str, v1: int, v2: int):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT version_number, layout FROM dashboard_versions WHERE dashboard_id = ? AND version_number IN (?, ?)", (id, v1, v2))
    rows = cursor.fetchall()
    conn.close()
    
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="Could not retrieve both versions for comparison")
        
    v_data = {r["version_number"]: json.loads(r["layout"]) for r in rows}
    
    # Calculate basic diffs (e.g. difference in number of cards or details)
    cards1 = v_data.get(v1, {}).get("cards", [])
    cards2 = v_data.get(v2, {}).get("cards", [])
    
    return {
        "status": "success",
        "version1": v1,
        "version2": v2,
        "cards_count_v1": len(cards1),
        "cards_count_v2": len(cards2),
        "added_cards": [c for c in cards2 if c.get("title") not in [x.get("title") for x in cards1]],
        "removed_cards": [c for c in cards1 if c.get("title") not in [x.get("title") for x in cards2]]
    }


# Favorites / Bookmarks Endpoints
@router.get("/favorites")
def list_favorites(username: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM favorites WHERE username = ? ORDER BY created_at DESC", (username,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@router.post("/favorites")
def add_favorite(payload: FavoriteCreate, user: dict = Depends(verify_token)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    fav_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO favorites (id, username, query, title) VALUES (?, ?, ?, ?)",
        (fav_id, payload.username, payload.query, payload.title)
    )
    conn.commit()
    conn.close()

    # Audit Log
    from backend.services.security import log_audit_action
    log_audit_action(payload.username, "Favorite Added", f"Favorited query: '{payload.title}'")

    return {"status": "success", "favorite_id": fav_id}
