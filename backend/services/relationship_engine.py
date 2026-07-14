import re
import uuid
import pandas as pd
import backend.config as config
import backend.services.history_db as db

class RelationshipEngine:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RelationshipEngine, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def discover_and_persist_relationships(self):
        """
        Scans all datasets in the database to discover PK/FK relationships and stores them.
        """
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM datasets")
        datasets = [dict(row) for row in cursor.fetchall()]
        
        # Load datasets into memory if not loaded
        loaded_dfs = {}
        from backend.services.loader import DATA_DIR
        import os
        for ds in datasets:
            if ds["type"] == "file":
                filepath = os.path.join(DATA_DIR, ds["filename"])
                if os.path.exists(filepath):
                    try:
                        ext = os.path.splitext(ds["filename"])[1].lower()
                        if ext == ".csv":
                            df = pd.read_csv(filepath, nrows=1000) # sample 1000 rows for distribution analysis
                        else:
                            df = pd.read_excel(filepath, nrows=1000)
                        loaded_dfs[ds["id"]] = (ds["name"], df)
                    except Exception:
                        pass

        discovered = []

        # Find relationships between all pairs of datasets
        ds_ids = list(loaded_dfs.keys())
        for i in range(len(ds_ids)):
            for j in range(i + 1, len(ds_ids)):
                id_a = ds_ids[i]
                id_b = ds_ids[j]
                name_a, df_a = loaded_dfs[id_a]
                name_b, df_b = loaded_dfs[id_b]

                for col_a in df_a.columns:
                    for col_b in df_b.columns:
                        # 1. Similarity heuristic for column names
                        clean_a = re.sub(r'[\s_\-]', '', col_a.lower())
                        clean_b = re.sub(r'[\s_\-]', '', col_b.lower())

                        is_similar_name = (
                            clean_a == clean_b or
                            (clean_a == "id" and clean_b == f"{name_a.lower().replace('_', '')}id") or
                            (clean_b == "id" and clean_a == f"{name_b.lower().replace('_', '')}id") or
                            clean_a == f"{clean_b}id" or
                            clean_b == f"{clean_a}id"
                        )

                        if not is_similar_name:
                            continue

                        # 2. Check overlap of unique values
                        set_a = set(df_a[col_a].dropna().unique())
                        set_b = set(df_b[col_b].dropna().unique())

                        if not set_a or not set_b:
                            continue

                        overlap = len(set_a.intersection(set_b))
                        min_len = min(len(set_a), len(set_b))

                        # If less than 20% overlap, ignore
                        if min_len > 0 and (overlap / min_len) < 0.20:
                            continue

                        # 3. Infer Cardinality
                        is_uniq_a = df_a[col_a].nunique() == len(df_a[col_a].dropna())
                        is_uniq_b = df_b[col_b].nunique() == len(df_b[col_b].dropna())

                        if is_uniq_a and is_uniq_b:
                            rel_type = "one_to_one"
                        elif is_uniq_a and not is_uniq_b:
                            rel_type = "one_to_many" # A (one) to B (many)
                        elif not is_uniq_a and is_uniq_b:
                            rel_type = "many_to_one" # A (many) to B (one)
                        else:
                            rel_type = "many_to_many"

                        confidence = 0.85 if overlap > 0 else 0.50

                        discovered.append({
                            "source_dataset_id": id_a,
                            "source_column": col_a,
                            "target_dataset_id": id_b,
                            "target_column": col_b,
                            "relationship_type": rel_type,
                            "confidence": confidence
                        })

        # Save discovered relationships to db (preventing duplicates)
        for rel in discovered:
            cursor.execute(
                """
                SELECT id FROM relationships 
                WHERE (source_dataset_id = ? AND source_column = ? AND target_dataset_id = ? AND target_column = ?)
                   OR (source_dataset_id = ? AND source_column = ? AND target_dataset_id = ? AND target_column = ?)
                """,
                (
                    rel["source_dataset_id"], rel["source_column"], rel["target_dataset_id"], rel["target_column"],
                    rel["target_dataset_id"], rel["target_column"], rel["source_dataset_id"], rel["source_column"]
                )
            )
            if not cursor.fetchone():
                cursor.execute(
                    """
                    INSERT INTO relationships (id, source_dataset_id, source_column, target_dataset_id, target_column, relationship_type, is_user_defined, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        str(uuid.uuid4()), rel["source_dataset_id"], rel["source_column"],
                        rel["target_dataset_id"], rel["target_column"], rel["relationship_type"],
                        rel["confidence"]
                    )
                )

        conn.commit()
        conn.close()

    def get_relationship_graph(self) -> dict:
        """
        Builds and returns relationship adjacency list.
        """
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM relationships")
        rels = [dict(row) for row in cursor.fetchall()]
        
        # Load dataset names for friendly mapping
        cursor.execute("SELECT id, name FROM datasets")
        ds_map = {row["id"]: row["name"] for row in cursor.fetchall()}
        conn.close()

        graph = {}
        for r in rels:
            src_name = ds_map.get(r["source_dataset_id"])
            tgt_name = ds_map.get(r["target_dataset_id"])
            if not src_name or not tgt_name:
                continue

            if src_name not in graph:
                graph[src_name] = []
            if tgt_name not in graph:
                graph[tgt_name] = []

            # Add edges
            graph[src_name].append({
                "to_table": tgt_name,
                "from_col": r["source_column"],
                "to_col": r["target_column"],
                "type": r["relationship_type"]
            })
            # Add inverse edge
            graph[tgt_name].append({
                "to_table": src_name,
                "from_col": r["target_column"],
                "to_col": r["source_column"],
                "type": "many_to_one" if r["relationship_type"] == "one_to_many" else ("one_to_many" if r["relationship_type"] == "many_to_one" else r["relationship_type"])
            })

        return graph

    def add_user_defined_relationship(self, src_id: str, src_col: str, tgt_id: str, tgt_col: str, rel_type: str) -> str:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        rel_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO relationships (id, source_dataset_id, source_column, target_dataset_id, target_column, relationship_type, is_user_defined, confidence)
            VALUES (?, ?, ?, ?, ?, ?, 1, 1.0)
            """,
            (rel_id, src_id, src_col, tgt_id, tgt_col, rel_type)
        )
        conn.commit()
        conn.close()
        return rel_id

    def delete_relationship(self, rel_id: str):
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM relationships WHERE id = ?", (rel_id,))
        conn.commit()
        conn.close()
