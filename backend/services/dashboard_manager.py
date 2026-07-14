import json
import uuid
from datetime import datetime
import backend.services.history_db as db

class DashboardManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DashboardManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def create_dashboard(self, title: str, layout: dict = None) -> str:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        dash_id = str(uuid.uuid4())
        layout_str = json.dumps(layout or {})
        
        cursor.execute(
            """
            INSERT INTO dashboards (id, title, layout, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (dash_id, title, layout_str, datetime.now(), datetime.now())
        )
        conn.commit()
        conn.close()
        return dash_id

    def get_dashboard(self, dash_id: str) -> dict:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dashboards WHERE id = ?", (dash_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            res = dict(row)
            res["layout"] = json.loads(res["layout"])
            return res
        return None

    def list_dashboards(self) -> list:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dashboards ORDER BY updated_at DESC")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for r in rows:
            r["layout"] = json.loads(r["layout"])
        return rows

    def update_dashboard(self, dash_id: str, title: str = None, layout: dict = None):
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if layout is not None:
            updates.append("layout = ?")
            params.append(json.dumps(layout))
            
        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now())
            params.append(dash_id)
            cursor.execute(
                f"UPDATE dashboards SET {', '.join(updates)} WHERE id = ?",
                tuple(params)
            )
            conn.commit()
        conn.close()

    def delete_dashboard(self, dash_id: str):
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dashboards WHERE id = ?", (dash_id,))
        conn.commit()
        conn.close()
