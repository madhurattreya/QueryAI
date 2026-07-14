import backend.services.history_db as db

class EnterpriseSearchService:
    def global_search(self, query: str) -> dict:
        """
        Executes keyword search across datasets, semantic models, dashboards, reports, and collaboration items.
        """
        q_clean = f"%{query.strip().lower()}%"
        conn = db.get_db_connection()
        cursor = conn.cursor()

        results = {
            "datasets": [],
            "semantic_model": [],
            "dashboards": [],
            "reports": [],
            "favorites": []
        }

        # 1. Search Datasets
        cursor.execute("SELECT id, name, type, source FROM datasets WHERE LOWER(name) LIKE ? OR LOWER(source) LIKE ?", (q_clean, q_clean))
        results["datasets"] = [dict(row) for row in cursor.fetchall()]

        # 2. Search Semantic Model (Measures/Dimensions)
        cursor.execute("SELECT id, dataset_id, name, type, expression, definition FROM semantic_model WHERE LOWER(name) LIKE ? OR LOWER(definition) LIKE ?", (q_clean, q_clean))
        results["semantic_model"] = [dict(row) for row in cursor.fetchall()]

        # 3. Search Dashboards
        cursor.execute("SELECT id, title, created_at FROM dashboards WHERE LOWER(title) LIKE ?", (q_clean,))
        results["dashboards"] = [dict(row) for row in cursor.fetchall()]

        # 4. Search Reports / Scheduler Jobs
        cursor.execute("SELECT id, dashboard_id, email_recipient, export_format FROM scheduler_jobs WHERE LOWER(email_recipient) LIKE ? OR LOWER(export_format) LIKE ?", (q_clean, q_clean))
        results["reports"] = [dict(row) for row in cursor.fetchall()]

        # 5. Search Favorites / Bookmarks
        cursor.execute("SELECT id, username, query, title FROM favorites WHERE LOWER(title) LIKE ? OR LOWER(query) LIKE ?", (q_clean, q_clean))
        results["favorites"] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return results
