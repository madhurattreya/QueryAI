"""
backend/models/execution_plan.py
──────────────────────────────────
Typed Pydantic models for all inter-layer contracts.
These models define the data shapes passed between:
  IntentParser → ColumnResolver → QueryPlanner → EngineRouter → ValidationLayer → Executor
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ─── Enums ────────────────────────────────────────────────────────────────────

class EngineType(str, Enum):
    PANDAS = "pandas"
    SQL = "sql"
    LLM = "llm"
    VISUALIZATION = "visualization"
    INSIGHT = "insight"
    METADATA = "metadata"
    GENERAL_CHAT = "general_chat"
    KPI_DASHBOARD = "kpi_dashboard"
    AMBIGUITY = "ambiguity"
    DASHBOARD_GEN = "dashboard_gen"


class IntentType(str, Enum):
    # Deterministic — handled without LLM
    HEAD = "head"
    TAIL = "tail"
    COUNT_ROWS = "count_rows"
    SUM = "sum"
    AVERAGE = "average"
    MIN_VALUE = "min_value"
    MAX_VALUE = "max_value"
    UNIQUE = "unique"
    DESCRIBE = "describe"
    SCHEMA_INFO = "schema_info"
    SORT_ASC = "sort_asc"
    SORT_DESC = "sort_desc"
    FILTER = "filter"
    GROUP_BY = "group_by"
    TOP_N = "top_n"
    BOTTOM_N = "bottom_n"
    DISTINCT = "distinct"
    NULL_CHECK = "null_check"
    SAMPLE = "sample"
    CORRELATION = "correlation"
    DTYPES = "dtypes"
    SHAPE = "shape"
    ID_LOOKUP = "id_lookup"
    # Complex — requires LLM or analytics lib
    AGGREGATION = "aggregation"
    ANALYTICS_LIB = "analytics_lib"
    LOOKUP = "lookup"
    RANKING = "ranking"
    VISUALIZATION = "visualization"
    PREDICTION = "prediction"
    GENERAL_CHAT = "general_chat"
    METADATA = "metadata"
    UNKNOWN = "unknown"


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ResolutionStrategy(str, Enum):
    EXACT = "exact"
    CASE_INSENSITIVE = "case_insensitive"
    WHITESPACE_NORMALIZED = "whitespace_normalized"
    UNDERSCORE_NORMALIZED = "underscore_normalized"
    LEVENSHTEIN = "levenshtein"
    RAPIDFUZZ_TOKEN_SORT = "rapidfuzz_token_sort"
    SEMANTIC = "semantic"
    LLM_HINT = "llm_hint"
    NOT_FOUND = "not_found"


# ─── Column resolution ────────────────────────────────────────────────────────

@dataclass
class ColumnMatch:
    """A single column candidate with confidence score and resolution strategy."""
    original_query: str
    matched_column: str
    confidence: float           # 0.0 – 1.0
    strategy: ResolutionStrategy
    dataset_name: str = ""


@dataclass
class ResolutionStep:
    """Records a single step in the column resolution pipeline."""
    step: int
    strategy: ResolutionStrategy
    query: str
    result: Optional[str]       # matched column name, or None
    confidence: float
    elapsed_ms: float


@dataclass
class ColumnResolutionResult:
    """Result of resolving a single column name query."""
    original_query: str
    resolved_column: Optional[str]      # None if not resolved
    confidence: float
    strategy_used: ResolutionStrategy
    steps: List[ResolutionStep] = field(default_factory=list)
    is_resolved: bool = False


# ─── Intent parsing ───────────────────────────────────────────────────────────

@dataclass
class IntentResult:
    """Output of the IntentParser for a given natural language question."""
    intent: IntentType
    confidence: float                   # 0.0 – 1.0
    params: Dict[str, Any] = field(default_factory=dict)
    is_deterministic: bool = False      # True if handled without LLM
    matched_patterns: List[str] = field(default_factory=list)


# ─── Validation ───────────────────────────────────────────────────────────────

@dataclass
class ValidationError:
    code: str                           # e.g. "COLUMN_NOT_FOUND", "NON_NUMERIC_AGG"
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    column: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    passed: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": [
                {"code": e.code, "message": e.message, "column": e.column, "suggestion": e.suggestion}
                for e in self.errors
            ],
            "warnings": [
                {"code": w.code, "message": w.message, "column": w.column, "suggestion": w.suggestion}
                for w in self.warnings
            ],
        }


# ─── Filter / Aggregation / Sort clauses ─────────────────────────────────────

@dataclass
class FilterClause:
    column: str
    operator: str           # "eq", "neq", "gt", "gte", "lt", "lte", "contains", "startswith"
    value: Any
    logical_relation: str = "and"   # "and" | "or"


@dataclass
class AggregationClause:
    column: str
    operator: str           # "sum", "mean", "count", "max", "min", "median", "std", "var"
    alias: Optional[str] = None


@dataclass
class SortClause:
    column: str
    ascending: bool = True


# ─── Execution Plan ───────────────────────────────────────────────────────────

@dataclass
class ExecutionPlan:
    """
    Typed, structured execution plan produced by QueryPlanner.
    Replaces the raw dict passed between layers in the legacy code.
    """
    intent: IntentType
    engine_type: EngineType
    confidence: float

    # Query parameters
    filters: List[FilterClause] = field(default_factory=list)
    aggregations: List[AggregationClause] = field(default_factory=list)
    groupby: List[str] = field(default_factory=list)
    sorting: List[SortClause] = field(default_factory=list)
    limit: Optional[int] = None
    offset: int = 0
    selected_columns: List[str] = field(default_factory=list)

    # Dataset context
    dataset_name: str = ""
    joined_datasets: List[str] = field(default_factory=list)

    # Resolution results
    column_resolution: Dict[str, ColumnResolutionResult] = field(default_factory=dict)
    validation_result: Optional[ValidationResult] = None

    # Debug metadata
    question: str = ""
    matched_patterns: List[str] = field(default_factory=list)
    recovery_steps: List[ResolutionStep] = field(default_factory=list)

    def to_debug_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "engine_type": self.engine_type.value,
            "confidence": self.confidence,
            "filters_count": len(self.filters),
            "aggregations": [{"col": a.column, "op": a.operator} for a in self.aggregations],
            "groupby": self.groupby,
            "sorting": [{"col": s.column, "asc": s.ascending} for s in self.sorting],
            "limit": self.limit,
            "selected_columns": self.selected_columns,
            "dataset_name": self.dataset_name,
            "validation": self.validation_result.to_dict() if self.validation_result else None,
            "column_resolution_steps": [
                {
                    "query": col,
                    "resolved": res.resolved_column,
                    "confidence": res.confidence,
                    "strategy": res.strategy_used.value,
                }
                for col, res in self.column_resolution.items()
            ],
        }


# ─── Debug metadata ───────────────────────────────────────────────────────────

@dataclass
class DebugMetadata:
    """
    Full observability payload attached to every query response.
    Extends the existing debug_info dict with typed, structured fields.
    """
    request_id: str = ""
    intent: str = ""
    engine_used: str = ""
    confidence_score: float = 0.0
    matched_columns: List[str] = field(default_factory=list)
    router_decision: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    generation_time_ms: float = 0.0
    execution_time_ms: float = 0.0
    total_time_ms: float = 0.0
    validation_result: Optional[Dict[str, Any]] = None
    recovery_steps: List[Dict[str, Any]] = field(default_factory=list)
    column_resolution_steps: List[Dict[str, Any]] = field(default_factory=list)
    cache_hit: bool = False
    llm_used: bool = False
    llm_timed_out: bool = False
    llm_retry_count: int = 0
    slowest_stage: str = ""
    timings: Dict[str, float] = field(default_factory=dict)
    complexity: str = "simple"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "intent": self.intent,
            "engine_used": self.engine_used,
            "confidence_score": self.confidence_score,
            "matched_columns": self.matched_columns,
            "router_decision": self.router_decision,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "generation_time_ms": self.generation_time_ms,
            "execution_time_ms": self.execution_time_ms,
            "total_time_ms": self.total_time_ms,
            "validation_result": self.validation_result,
            "recovery_steps": self.recovery_steps,
            "column_resolution_steps": self.column_resolution_steps,
            "cache_hit": self.cache_hit,
            "llm_used": self.llm_used,
            "llm_timed_out": self.llm_timed_out,
            "llm_retry_count": self.llm_retry_count,
            "slowest_stage": self.slowest_stage,
            "timings": self.timings,
            "complexity": self.complexity,
        }
