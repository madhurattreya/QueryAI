"""
backend/services/schema_rag.py
───────────────────────────────
Schema RAG (Retrieval-Augmented Generation) & Semantic Search Engine.

Indexes table names, column descriptions, and metric definitions using TF-IDF / term vector scoring.
Prunes large database schemas (100+ tables, 1000+ columns) to return only top-k relevant tables/columns
for LLM prompt context injection, drastically reducing token consumption and eliminating context limits.
"""

from __future__ import annotations
import math
import re
from typing import Dict, List, Any, Tuple

class SchemaRAGIndex:
    """
    In-memory TF-IDF Vector Index for schema retrieval and semantic pruning.
    """

    def __init__(self):
        self.table_docs: Dict[str, Dict[str, Any]] = {}
        self.doc_vectors: Dict[str, Dict[str, float]] = {}
        self.idf: Dict[str, float] = {}

    def index_datasets(self, datasets_schema: Dict[str, Dict[str, Any]]) -> None:
        """
        Indexes dataset metadata.
        
        datasets_schema format:
        {
          "table_name": {
             "columns": ["col1", "col2", ...],
             "dtypes": {"col1": "int64", ...},
             "sample_rows": [...],
             "description": "Optional text description"
          }
        }
        """
        self.table_docs = {}
        tokens_per_doc: Dict[str, List[str]] = {}
        df_counts: Dict[str, int] = {}
        total_docs = len(datasets_schema)

        if total_docs == 0:
            return

        for table_name, schema in datasets_schema.items():
            cols = schema.get("columns", [])
            desc = schema.get("description", "")
            
            # Combine table name, column names, and description into searchable text document
            text_corpus = f"{table_name} " + " ".join(cols) + f" {desc}"
            tokens = self._tokenize(text_corpus)
            tokens_per_doc[table_name] = tokens
            self.table_docs[table_name] = schema

            # Calculate document frequency
            unique_tokens = set(tokens)
            for t in unique_tokens:
                df_counts[t] = df_counts.get(t, 0) + 1

        # Calculate IDF
        for t, count in df_counts.items():
            self.idf[t] = math.log((total_docs + 1) / (count + 1)) + 1.0

        # Calculate TF-IDF vectors
        for table_name, tokens in tokens_per_doc.items():
            tf: Dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1

            vec: Dict[str, float] = {}
            doc_len = len(tokens) or 1
            for t, count in tf.items():
                vec[t] = (count / doc_len) * self.idf.get(t, 1.0)
            self.doc_vectors[table_name] = vec

    def retrieve_top_k(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Retrieves top_k most relevant tables for the given natural language user query.
        Returns list of (table_name, relevance_score).
        """
        if not self.doc_vectors:
            return [(name, 1.0) for name in self.table_docs.keys()][:top_k]

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return [(name, 1.0) for name in list(self.table_docs.keys())[:top_k]]

        query_tf: Dict[str, int] = {}
        for t in query_tokens:
            query_tf[t] = query_tf.get(t, 0) + 1

        q_len = len(query_tokens)
        query_vec = {t: (cnt / q_len) * self.idf.get(t, 1.0) for t, cnt in query_tf.items()}

        scores: List[Tuple[str, float]] = []
        for table_name, doc_vec in self.doc_vectors.items():
            score = self._cosine_similarity(query_vec, doc_vec)

            # Boost if query explicitly mentions table name
            if table_name.lower() in query.lower():
                score += 0.5

            scores.append((table_name, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _tokenize(self, text: str) -> List[str]:
        cleaned = re.sub(r'[^a-zA-Z0-9_\s]', ' ', text.lower())
        tokens = [t for t in cleaned.split() if len(t) > 1]
        return tokens

    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        common_keys = set(vec1.keys()) & set(vec2.keys())
        if not common_keys:
            return 0.0

        dot_product = sum(vec1[k] * vec2[k] for k in common_keys)
        mag1 = math.sqrt(sum(v * v for v in vec1.values()))
        mag2 = math.sqrt(sum(v * v for v in vec2.values()))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)


# Global singleton instance
schema_rag = SchemaRAGIndex()
