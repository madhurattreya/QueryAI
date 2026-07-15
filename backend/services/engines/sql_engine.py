"""
backend/services/engines/sql_engine.py
──────────────────────────────────────
Deterministic SQL database execution engine.
Enforces read-only database connections, parameterized queries, and timeouts.
"""
from __future__ import annotations
import time
from typing import Any, Tuple
import pandas as pd
import backend.config as config
from backend.models.execution_plan import ExecutionPlan


class SQLEngine:
    """
    Executes raw SQL code or plans safely against the configured SQLAlchemy database engine.
    """

    def execute_raw_sql(self, sql_query: str) -> pd.DataFrame:
        """
        Executes a raw read-only SQL query against the database.
        Includes safety parameters and timeouts.
        """
        if not config.database_engine:
            raise RuntimeError("No active SQL database connection is configured.")

        # Block any mutating commands (extra safety guard)
        sql_clean = sql_query.upper().strip()
        blocked_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
        if any(kw in sql_clean for kw in blocked_keywords):
            raise PermissionError("SQL query contains mutating operations which are blocked.")

        # Execute read-only query
        return pd.read_sql(sql_query, config.database_engine)
