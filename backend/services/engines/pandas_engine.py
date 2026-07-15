"""
backend/services/engines/pandas_engine.py
──────────────────────────────────────────
Deterministic Pandas Execution Engine.
Wraps execute_parsed_query from query_engine.py using vectorized Pandas operations.
"""
from __future__ import annotations
import time
from typing import Any, Dict, Optional, Tuple
import pandas as pd
import backend.config as config
from backend.models.execution_plan import ExecutionPlan
from backend.services.query_engine import execute_parsed_query


class PandasEngine:
    """
    Executes a structured execution plan against in-memory Pandas DataFrames.
    """

    def execute(self, plan: ExecutionPlan, df: pd.DataFrame, df_name: str = "df") -> Tuple[Any, str]:
        """
        Executes the plan deterministically against the DataFrame.
        Returns: (result_data, pandas_expression_str)
        """
        # Map ExecutionPlan to legacy ParsedQuery for query_engine execution path
        from backend.services.query_parser import ParsedQuery
        
        legacy_filters = [{"column": f.column, "operator": f.operator, "value": f.value} for f in plan.filters]
        legacy_aggs = [{"column": a.column, "operator": a.operator} for a in plan.aggregations]
        legacy_sorts = [{"column": s.column, "ascending": s.ascending} for s in plan.sorting]
        
        parsed = ParsedQuery(
            intent=plan.intent.value,
            confidence=plan.confidence,
            filters=legacy_filters,
            aggregations=legacy_aggs,
            sorting=legacy_sorts,
            execution_plan={
                "intent": plan.intent.value,
                "groupby": plan.groupby,
                "limit": plan.limit,
                "offset": plan.offset,
            }
        )
        
        # Call deterministic query engine
        result, code_expr = execute_parsed_query(parsed, df, df_name=df_name)
        return result, code_expr
