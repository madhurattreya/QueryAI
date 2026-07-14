import uuid
import backend.services.history_db as db

class CollaborationService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(CollaborationService, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def add_comment(self, dashboard_id: str, username: str, comment_text: str) -> str:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        comment_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO comments (id, dashboard_id, username, comment)
            VALUES (?, ?, ?, ?)
            """,
            (comment_id, dashboard_id, username, comment_text)
        )
        conn.commit()
        conn.close()
        return comment_id

    def get_comments(self, dashboard_id: str) -> list:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM comments WHERE dashboard_id = ? ORDER BY created_at ASC", (dashboard_id,))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def add_favorite(self, username: str, query: str, title: str) -> str:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        fav_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO favorites (id, username, query, title)
            VALUES (?, ?, ?, ?)
            """,
            (fav_id, username, query, title)
        )
        conn.commit()
        conn.close()
        return fav_id

    def get_favorites(self, username: str = None) -> list:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        if username:
            cursor.execute("SELECT * FROM favorites WHERE username = ? ORDER BY created_at DESC", (username,))
        else:
            cursor.execute("SELECT * FROM favorites ORDER BY created_at DESC")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def delete_favorite(self, fav_id: str):
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favorites WHERE id = ?", (fav_id,))
        conn.commit()
        conn.close()
