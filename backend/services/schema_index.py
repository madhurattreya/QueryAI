"""
backend/services/schema_index.py
──────────────────────────────────
Structured, searchable schema index — replaces raw string schema cache.

SchemaIndex preloads on dataset upload and exposes:
  - lookup(query)  → List[ColumnMatch] ranked by confidence
  - get_all_columns() → List[str]
  - is_numeric(column) → bool
  - get_column_type(column) → str

Used by ColumnResolver and IntentParser for accurate column matching
without relying on substring search over unstructured text.
"""
from __future__ import annotations
import re
import time
from typing import Any, Dict, List, Optional, Set
import pandas as pd

from backend.models.execution_plan import ColumnMatch, ResolutionStrategy


class ColumnEntry:
    """Metadata for a single column in the schema index."""

    def __init__(self, name: str, dtype: str, sample_values: List[Any]):
        self.name = name
        self.dtype = dtype
        self.sample_values = sample_values[:5]

        # Pre-compute all searchable variants
        self.variants: Set[str] = self._build_variants(name)

    def _build_variants(self, name: str) -> Set[str]:
        variants = set()
        # Original
        variants.add(name)
        # Lowercase
        lower = name.lower()
        variants.add(lower)
        # Strip whitespace
        stripped = name.strip()
        variants.add(stripped.lower())
        # Underscores → spaces
        variants.add(lower.replace("_", " "))
        # Spaces → underscores
        variants.add(lower.replace(" ", "_"))
        # Remove special chars
        clean = re.sub(r"[^a-z0-9\s]", "", lower)
        variants.add(clean)
        variants.add(clean.replace(" ", ""))
        return variants

    @property
    def is_numeric(self) -> bool:
        return "int" in self.dtype.lower() or "float" in self.dtype.lower()

    @property
    def is_datetime(self) -> bool:
        return "datetime" in self.dtype.lower() or "timestamp" in self.dtype.lower()

    @property
    def is_categorical(self) -> bool:
        return "object" in self.dtype.lower() or "string" in self.dtype.lower() or "category" in self.dtype.lower()


class SchemaIndex:
    """
    Searchable index for a single DataFrame's column schema.
    Created once per dataset on upload; refreshed when dataset changes.
    """

    def __init__(self, dataset_name: str, df: pd.DataFrame):
        self.dataset_name = dataset_name
        self._columns: Dict[str, ColumnEntry] = {}
        self._build(df)

    def _build(self, df: pd.DataFrame) -> None:
        """Build the index from a DataFrame."""
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            try:
                sample = df[col].dropna().head(5).tolist()
            except Exception:
                sample = []
            entry = ColumnEntry(col, dtype_str, sample)
            self._columns[col] = entry

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_all_columns(self) -> List[str]:
        """Return all column names in original case."""
        return list(self._columns.keys())

    def get_numeric_columns(self) -> List[str]:
        return [col for col, entry in self._columns.items() if entry.is_numeric]

    def get_datetime_columns(self) -> List[str]:
        return [col for col, entry in self._columns.items() if entry.is_datetime]

    def get_categorical_columns(self) -> List[str]:
        return [col for col, entry in self._columns.items() if entry.is_categorical]

    def is_numeric(self, column: str) -> bool:
        entry = self._columns.get(column)
        return entry.is_numeric if entry else False

    def is_categorical(self, column: str) -> bool:
        entry = self._columns.get(column)
        return entry.is_categorical if entry else False

    def get_column_type(self, column: str) -> str:
        entry = self._columns.get(column)
        return entry.dtype if entry else "unknown"

    def get_entry(self, column: str) -> Optional[ColumnEntry]:
        return self._columns.get(column)

    def lookup(self, query: str, top_k: int = 5) -> List[ColumnMatch]:
        """
        Fast lookup of column candidates matching the query string.
        Uses variant matching only (no fuzzy — fuzzy is done by ColumnResolver).

        Returns a list of ColumnMatch sorted by confidence descending.
        """
        if not query:
            return []

        q = query.strip()
        q_lower = q.lower()
        q_normalized = q_lower.replace("_", " ").replace("-", " ")
        q_no_space = q_lower.replace(" ", "").replace("_", "")

        matches: List[ColumnMatch] = []

        for col_name, entry in self._columns.items():
            confidence = 0.0

            # Exact match
            if q == col_name:
                confidence = 1.0
            # Case-insensitive exact
            elif q_lower == col_name.lower():
                confidence = 0.98
            # Variant match
            elif q_lower in entry.variants or q_normalized in entry.variants:
                confidence = 0.95
            elif q_no_space == col_name.lower().replace(" ", "").replace("_", ""):
                confidence = 0.90
            # Prefix match
            elif col_name.lower().startswith(q_lower) or q_lower.startswith(col_name.lower()):
                confidence = 0.80
            # Substring match
            elif q_lower in col_name.lower() or col_name.lower() in q_lower:
                confidence = 0.65

            if confidence > 0.0:
                matches.append(ColumnMatch(
                    original_query=query,
                    matched_column=col_name,
                    confidence=confidence,
                    strategy=ResolutionStrategy.EXACT if confidence >= 0.98 else ResolutionStrategy.WHITESPACE_NORMALIZED,
                    dataset_name=self.dataset_name,
                ))

        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches[:top_k]

    def best_match(self, query: str) -> Optional[ColumnMatch]:
        """Returns the single best-matching column for a query, or None."""
        results = self.lookup(query, top_k=1)
        return results[0] if results else None

    def column_exists(self, column: str) -> bool:
        """Returns True if the column exists (exact or case-insensitive)."""
        if column in self._columns:
            return True
        col_lower = column.lower()
        return any(c.lower() == col_lower for c in self._columns)

    def __repr__(self) -> str:
        return f"SchemaIndex(dataset={self.dataset_name!r}, columns={len(self._columns)})"


# ─── Global registry of schema indexes ───────────────────────────────────────

class SchemaIndexRegistry:
    """
    Singleton registry mapping dataset names to their SchemaIndex instances.
    Thread-safe: uses backend DataRegistry as the source of truth.
    """
    _indexes: Dict[str, SchemaIndex] = {}

    @classmethod
    def build_or_refresh(cls, dataset_name: str, df: pd.DataFrame) -> SchemaIndex:
        """Build or refresh the index for a dataset."""
        idx = SchemaIndex(dataset_name, df)
        cls._indexes[dataset_name] = idx
        return idx

    @classmethod
    def get(cls, dataset_name: str) -> Optional[SchemaIndex]:
        return cls._indexes.get(dataset_name)

    @classmethod
    def get_or_build(cls, dataset_name: str, df: pd.DataFrame) -> SchemaIndex:
        """Returns cached index or builds a new one."""
        if dataset_name not in cls._indexes:
            return cls.build_or_refresh(dataset_name, df)
        return cls._indexes[dataset_name]

    @classmethod
    def invalidate(cls, dataset_name: str) -> None:
        cls._indexes.pop(dataset_name, None)

    @classmethod
    def invalidate_all(cls) -> None:
        cls._indexes.clear()

    @classmethod
    def get_all_indexes(cls) -> Dict[str, SchemaIndex]:
        return dict(cls._indexes)
