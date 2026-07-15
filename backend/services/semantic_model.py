import uuid
import backend.services.history_db as db

class SemanticModelManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SemanticModelManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def add_model_item(self, dataset_id: str, name: str, item_type: str, expression: str, definition: str = "",
                       display_name: str = "", description: str = "", business_meaning: str = "", synonyms: str = "",
                       units: str = "", aggregation: str = "", category: str = "", is_measure: int = 0, is_dimension: int = 0,
                       hierarchy: str = "") -> str:
        """
        Adds a semantic item (dimension, measure, calculation, hierarchy) to the semantic model.
        """
        conn = db.get_db_connection()
        cursor = conn.cursor()
        item_id = str(uuid.uuid4())
        
        cursor.execute(
            """
            INSERT INTO semantic_model (
                id, dataset_id, name, type, expression, definition,
                display_name, description, business_meaning, synonyms,
                units, aggregation, category, is_measure, is_dimension, hierarchy
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id, dataset_id, name, item_type, expression, definition,
                display_name, description, business_meaning, synonyms,
                units, aggregation, category, is_measure, is_dimension, hierarchy
            )
        )
        conn.commit()
        conn.close()
        return item_id

    def get_model_items(self, dataset_id: str = None) -> list:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        if dataset_id:
            cursor.execute("SELECT * FROM semantic_model WHERE dataset_id = ?", (dataset_id,))
        else:
            cursor.execute("SELECT * FROM semantic_model")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_model_item_by_name(self, name: str, dataset_id: str) -> dict:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM semantic_model WHERE name = ? AND dataset_id = ? LIMIT 1", (name, dataset_id))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def delete_model_item(self, item_id: str):
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM semantic_model WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()

    def get_hierarchies(self, dataset_id: str) -> list:
        """
        Retrieves list of hierarchies parsed from semantic model expressions.
        Expression format: "Country -> State -> City"
        """
        items = self.get_model_items(dataset_id)
        hierarchies = []
        for item in items:
            if item["type"] == "hierarchy":
                levels = [lvl.strip() for lvl in item["expression"].split("->")]
                hierarchies.append({
                    "id": item["id"],
                    "name": item["name"],
                    "levels": levels,
                    "definition": item["definition"]
                })
        return hierarchies
