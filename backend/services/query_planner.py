"""
backend/services/query_planner.py
──────────────────────────────────
Compiles natural language query, intent, schema metadata, and resolved columns
into a unified, typed ExecutionPlan dataclass.

Determines the target engine (Pandas, SQL, LLM, Metadata, General Chat)
based on intent confidence thresholds.
"""
from __future__ import annotations
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import backend.config as config
from backend.models.execution_plan import (
    AggregationClause,
    EngineType,
    ExecutionPlan,
    FilterClause,
    IntentType,
    SortClause,
    ValidationError,
    ValidationResult,
)
from backend.services.column_resolver import ColumnResolver
from backend.services.intent_parser import IntentParser
from backend.services.schema_index import SchemaIndex, SchemaIndexRegistry
from backend.services.validation_layer import ValidationLayer


class QueryPlanner:
    """
    Orchestrates Intent Parsing, Column Resolution, and Pre-Execution Validation.
    Outputs a structured, validated ExecutionPlan.
    """

    def __init__(self, dataset_name: Optional[str] = None):
        self.dataset_name = dataset_name
        self.schema_index = SchemaIndexRegistry.get(dataset_name) if dataset_name else None
        self.intent_parser = IntentParser(self.schema_index)
        self.resolver = ColumnResolver(self.schema_index) if self.schema_index else None
        self.validator = ValidationLayer(dataset_name)

    def plan(self, question: str) -> ExecutionPlan:
        """
        Creates an ExecutionPlan for the user query.
        """
        t_start = time.time()
        q = question.lower().strip()
        from backend.services.query_parser import rewrite_query
        q_rewritten = rewrite_query(question)
        
        # 1. Parse Intent Deterministically
        intent_res = self.intent_parser.parse(q_rewritten)

        # 2. Determine target execution engine
        engine = EngineType.LLM  # default fallback
        confidence = intent_res.confidence

        # Determine default engine based on source type
        source_type = config.current_source_type  # "file" or "sql"
        default_engine = EngineType.PANDAS if source_type == "file" else EngineType.SQL

        if intent_res.is_deterministic and intent_res.confidence >= config.app_settings.confidence_threshold_deterministic:
            if intent_res.intent in [IntentType.SCHEMA_INFO, IntentType.DTYPES]:
                engine = EngineType.METADATA
            elif intent_res.intent in [IntentType.DESCRIBE, IntentType.SHAPE]:
                engine = default_engine
            elif intent_res.intent in [IntentType.HEAD, IntentType.TAIL, IntentType.SAMPLE, IntentType.COUNT_ROWS, IntentType.GROUP_BY]:
                engine = default_engine
            elif intent_res.intent in [IntentType.AVERAGE, IntentType.SUM, IntentType.MIN_VALUE, IntentType.MAX_VALUE, IntentType.UNIQUE, IntentType.NULL_CHECK]:
                engine = default_engine
            elif intent_res.intent in [IntentType.TOP_N, IntentType.BOTTOM_N]:
                engine = default_engine

        # General chat bypass keywords
        chat_keywords = ["hello", "hi", "hey", "who are you", "what is queryiq", "help me", "greetings"]
        if any(w == q.split()[0] if q.split() else False for w in chat_keywords):
            engine = EngineType.GENERAL_CHAT
            intent_res.intent = IntentType.GENERAL_CHAT
            confidence = 1.0

        # KPI dashboard bypass
        from backend.services.kpi_engine import is_kpi_dashboard_query
        if is_kpi_dashboard_query(question):
            engine = EngineType.KPI_DASHBOARD
            intent_res.intent = IntentType.ANALYTICS_LIB
            confidence = 1.0

        # Build initial ExecutionPlan
        plan = ExecutionPlan(
            intent=intent_res.intent,
            engine_type=engine,
            confidence=confidence,
            dataset_name=self.dataset_name or "",
            question=question,
            matched_patterns=intent_res.matched_patterns,
        )

        # 2.5. Retrieve active filters from legacy parser to preserve exact filtering context
        legacy_validation_failed = False
        try:
            from backend.services.query_parser import parse_question
            active_df = None
            if config.datasets and self.dataset_name:
                active_df = config.datasets.get(self.dataset_name)
            
            parsed_legacy = parse_question(question, active_df, self.dataset_name or "")
            if parsed_legacy:
                if parsed_legacy.confidence == 0.0:
                    legacy_validation_failed = True
                if parsed_legacy.filters:
                    # Map extracted filters to FilterClause list
                    for f in parsed_legacy.filters:
                        plan.filters.append(FilterClause(
                            column=f["column"],
                            operator=f["operator"],
                            value=f["value"]
                        ))
        except Exception as e:
            print(f"[PLANNER CONTEXT WARNING] Failed to import legacy parser context: {e}")

        # 3. Resolve columns and map parameters for deterministic intents
        if intent_res.is_deterministic and self.schema_index:
            self._map_deterministic_params(plan, intent_res.intent, intent_res.params)

        # 4. Perform pre-execution validation
        if engine == EngineType.PANDAS:
            # We mock the pandas code structure for basic validation prior to sandbox
            expr = self._mock_pandas_expression(plan)
            val_res = self.validator.validate_python_code(f"result = {expr}")
            plan.validation_result = val_res
        elif engine == EngineType.SQL:
            sql_expr = self._mock_sql_query(plan)
            val_res = self.validator.validate_sql_query(sql_expr)
            plan.validation_result = val_res

        if legacy_validation_failed:
            plan.confidence = 0.0
            plan.engine_type = EngineType.LLM

        return plan

    def _map_deterministic_params(self, plan: ExecutionPlan, intent: IntentType, params: Dict[str, Any]) -> None:
        """Maps parser parameters into structured execution clauses."""
        if not self.schema_index or not self.resolver:
            return

        # Handle columns
        col_param = params.get("column")
        resolved_col = None
        if col_param:
            res = self.resolver.resolve(col_param)
            plan.column_resolution[col_param] = res
            plan.recovery_steps.extend(res.steps)
            if res.is_resolved:
                resolved_col = res.resolved_column
                plan.selected_columns = [resolved_col]

        # Handle Head/Tail/Sample limits
        limit_param = params.get("limit")
        if limit_param is not None:
            plan.limit = limit_param

        # Match parameters to clauses
        if intent == IntentType.HEAD:
            plan.limit = plan.limit or 5
        elif intent == IntentType.TAIL:
            plan.limit = plan.limit or 5
        elif intent == IntentType.SAMPLE:
            plan.limit = plan.limit or 5
        elif intent == IntentType.COUNT_ROWS:
            plan.aggregations = [AggregationClause(column=self.schema_index.get_all_columns()[0], operator="count")]
        elif intent == IntentType.AVERAGE and resolved_col:
            plan.aggregations = [AggregationClause(column=resolved_col, operator="mean")]
        elif intent == IntentType.SUM and resolved_col:
            plan.aggregations = [AggregationClause(column=resolved_col, operator="sum")]
        elif intent == IntentType.MIN_VALUE and resolved_col:
            plan.aggregations = [AggregationClause(column=resolved_col, operator="min")]
        elif intent == IntentType.MAX_VALUE and resolved_col:
            plan.aggregations = [AggregationClause(column=resolved_col, operator="max")]
        elif intent == IntentType.UNIQUE and resolved_col:
            # We want unique values listed
            plan.selected_columns = [resolved_col]
        elif intent == IntentType.TOP_N and resolved_col:
            plan.sorting = [SortClause(column=resolved_col, ascending=False)]
            plan.limit = plan.limit or 5
        elif intent == IntentType.BOTTOM_N and resolved_col:
            plan.sorting = [SortClause(column=resolved_col, ascending=True)]
            plan.limit = plan.limit or 5
        elif intent == IntentType.GROUP_BY and resolved_col:
            plan.groupby = [resolved_col]
            plan.aggregations = [AggregationClause(column=resolved_col, operator="count")]
            plan.selected_columns = [resolved_col]

    def _mock_pandas_expression(self, plan: ExecutionPlan) -> str:
        """Simulates the final pandas code expression for static analysis."""
        df_ref = plan.dataset_name or "df"
        expr = df_ref

        if plan.intent == IntentType.HEAD:
            expr += f".head({plan.limit})"
        elif plan.intent == IntentType.TAIL:
            expr += f".tail({plan.limit})"
        elif plan.intent == IntentType.SAMPLE:
            expr += f".sample({plan.limit})"
        elif plan.intent == IntentType.COUNT_ROWS:
            expr = f"len({df_ref})"
        elif plan.groupby:
            expr += f".groupby('{plan.groupby[0]}').size().reset_index(name='count')"
        elif plan.aggregations:
            agg = plan.aggregations[0]
            expr += f"['{agg.column}'].{agg.operator}()"
        elif plan.sorting:
            sort = plan.sorting[0]
            expr += f".sort_values(by='{sort.column}', ascending={sort.ascending})"
            if plan.limit:
                expr += f".head({plan.limit})"
        return expr

    def _mock_sql_query(self, plan: ExecutionPlan) -> str:
        """Simulates the final SQL query for syntax and validation."""
        table_ref = plan.dataset_name or "table"
        
        if plan.intent == IntentType.COUNT_ROWS:
            return f"SELECT COUNT(*) FROM {table_ref}"
        
        cols = ", ".join(plan.selected_columns) if plan.selected_columns else "*"
        query = f"SELECT {cols} FROM {table_ref}"
        
        if plan.sorting:
            sort = plan.sorting[0]
            dir_str = "ASC" if sort.ascending else "DESC"
            query += f" ORDER BY {sort.column} {dir_str}"
            
        if plan.limit:
            query += f" LIMIT {plan.limit}"
            
        return query
