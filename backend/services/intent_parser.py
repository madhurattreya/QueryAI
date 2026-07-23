"""
backend/services/intent_parser.py
──────────────────────────────────
Deterministic, rule-based intent parser.
Matches common query patterns using regular expressions.
If matching confidence is >= 0.80, routes the query path
directly to deterministic execution, bypassing the LLM.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple
import backend.config as config
from backend.models.execution_plan import IntentResult, IntentType
from backend.services.schema_index import SchemaIndex, SchemaIndexRegistry


class IntentParser:
    """
    Deterministic query intent parser.
    Analyzes natural language questions against common SQL/Pandas operators.
    """

    def __init__(self, schema_index: Optional[SchemaIndex] = None):
        self.schema_index = schema_index

    def parse(self, question: str) -> IntentResult:
        """
        Parses a natural language question to identify deterministic intents.
        """
        q = question.lower().strip()
        q_clean = re.sub(r"[^\w\s]", "", q)  # remove punctuation

        # ─── 1. Schema Info & Metadata Intents ──────────────────────────────
        if any(w in q_clean for w in ["show columns", "list columns", "get columns", "what columns", "columns list", "what are the columns", "show schema", "table schema", "view schema"]):
            return IntentResult(
                intent=IntentType.SCHEMA_INFO,
                confidence=1.0,
                is_deterministic=True,
                matched_patterns=["schema_info_keywords"],
            )

        if any(w in q_clean for w in ["data types", "column types", "dtypes", "show types", "list types"]):
            return IntentResult(
                intent=IntentType.DTYPES,
                confidence=1.0,
                is_deterministic=True,
                matched_patterns=["dtypes_keywords"],
            )

        describe_phrases = [
            "describe dataset", "summary statistics", "stats summary", "summarize dataset", "dataset summary", 
            "summary of dataset", "is data me kya hai", "kya hai is data me", "kisliye hai ye data", 
            "data kis se related hai", "upload kiya", "uploaded data", "about this dataset", 
            "what is in this dataset", "what is this data", "explain dataset", "explain data", "dataset overview"
        ]
        if any(w in q_clean for w in describe_phrases):
            return IntentResult(
                intent=IntentType.DESCRIBE,
                confidence=0.95,
                is_deterministic=True,
                matched_patterns=["describe_keywords"],
            )

        if any(w in q_clean for w in ["shape of", "dataset shape", "number of rows and columns", "how many rows and columns", "how many columns and rows", "size of dataset"]):
            return IntentResult(
                intent=IntentType.SHAPE,
                confidence=1.0,
                is_deterministic=True,
                matched_patterns=["shape_keywords"],
            )

        # ─── 2. Row Count Intents ───────────────────────────────────────────
        if any(p in q_clean for p in ["how many rows", "number of rows", "total rows", "row count", "count rows", "how many records", "total records", "number of records", "count of records", "how many items", "total items"]):
            return IntentResult(
                intent=IntentType.COUNT_ROWS,
                confidence=0.95,
                is_deterministic=True,
                matched_patterns=["count_rows_keywords"],
            )

        # ─── 3. Head / Tail / Sample Intents ────────────────────────────────
        # Match head: "show first 5", "first 10 records", etc.
        head_match = re.search(
            r"\b(show|get|print|list|display)?\s*(first|top|head)\s*(\d+)?\s*(rows|records|lines|entries|items|values)?\b",
            q_clean
        )
        if head_match and "top" not in q_clean:  # Skip 'top N by column' which is ranking
            limit = int(head_match.group(3)) if head_match.group(3) else 5
            return IntentResult(
                intent=IntentType.HEAD,
                confidence=0.90,
                is_deterministic=True,
                params={"limit": limit},
                matched_patterns=["head_regex"],
            )

        # Match tail: "show last 5", "last 10 records", etc.
        tail_match = re.search(
            r"\b(show|get|print|list|display)?\s*(last|bottom|tail)\s*(\d+)?\s*(rows|records|lines|entries|items|values)?\b",
            q_clean
        )
        if tail_match and "bottom" not in q_clean:  # Skip 'bottom N by column' which is ranking
            limit = int(tail_match.group(3)) if tail_match.group(3) else 5
            return IntentResult(
                intent=IntentType.TAIL,
                confidence=0.90,
                is_deterministic=True,
                params={"limit": limit},
                matched_patterns=["tail_regex"],
            )

        # Match sample: "show sample of 10", "get 5 random rows"
        sample_match = re.search(
            r"\b(show|get|print|list|display)?\s*(sample|random)\s*(\d+)?\s*(rows|records|lines|entries|items|values)?\b",
            q_clean
        )
        if sample_match:
            limit = int(sample_match.group(3)) if sample_match.group(3) else 5
            return IntentResult(
                intent=IntentType.SAMPLE,
                confidence=0.90,
                is_deterministic=True,
                params={"limit": limit},
                matched_patterns=["sample_regex"],
            )

        # ─── 4. Column Specific Basic Statistics ────────────────────────────
        if self.schema_index:
            # We look for simple expressions like "average of <col>", "mean <col>", "sum of <col>", "min of <col>", "max of <col>"
            words = q_clean.split()
            cols = self.schema_index.get_all_columns()
            
            # Skip simple scalar intents if question contains group-by, dimension, ratio, or analytical indicators
            has_complex_analytical_intent = any(w in q_clean for w in [
                "each", "in each", "for each", "within each", "across", "per", "by", "wise", "monthly", "quarterly", "year", "month", "quarter",
                "rank", "compare", "pivot", "dashboard", "trend", "margin", "contribution", "percentage", "percent", "%",
                "ratio", "divide", "divided", "÷", "versus", "vs"
            ]) or any(qw in q_clean for qw in [
                "which salesperson", "which month", "which product", "which customer", "which region",
                "which city", "which state", "which category", "who", "what salesperson", "what month",
                "what product", "what customer", "what region", "what city", "what category"
            ])

            if not has_complex_analytical_intent:
                # Simple average/mean match
                avg_keywords = ["average", "avg", "mean", "avg of", "mean of", "average of"]
                for kw in avg_keywords:
                    if kw in q_clean:
                        for col in cols:
                            if col.lower() in q_clean and self.schema_index.is_numeric(col):
                                return IntentResult(
                                    intent=IntentType.AVERAGE,
                                    confidence=0.85,
                                    is_deterministic=True,
                                    params={"column": col},
                                    matched_patterns=["average_col_match"],
                                )

                # Simple sum/total match
                sum_keywords = ["sum", "total", "sum of", "total of", "summation of"]
                for kw in sum_keywords:
                    if kw in q_clean:
                        for col in cols:
                            if col.lower() in q_clean and self.schema_index.is_numeric(col):
                                # Ensure we don't confuse with count/average keywords in same query
                                if not any(w in q_clean for w in ["avg", "mean", "average", "count", "how many"]):
                                    return IntentResult(
                                        intent=IntentType.SUM,
                                        confidence=0.85,
                                        is_deterministic=True,
                                        params={"column": col},
                                        matched_patterns=["sum_col_match"],
                                    )

                # Simple min match
                min_keywords = ["minimum", "min", "lowest", "smallest", "min of", "minimum of"]
                for kw in min_keywords:
                    if kw in q_clean:
                        for col in cols:
                            if col.lower() in q_clean:
                                return IntentResult(
                                    intent=IntentType.MIN_VALUE,
                                    confidence=0.85,
                                    is_deterministic=True,
                                    params={"column": col},
                                    matched_patterns=["min_col_match"],
                                )

                # Simple max match
                max_keywords = ["maximum", "max", "highest", "largest", "max of", "maximum of"]
                for kw in max_keywords:
                    if kw in q_clean:
                        for col in cols:
                            if col.lower() in q_clean:
                                return IntentResult(
                                    intent=IntentType.MAX_VALUE,
                                    confidence=0.85,
                                    is_deterministic=True,
                                    params={"column": col},
                                    matched_patterns=["max_col_match"],
                                )

            # Simple unique/distinct match
            uniq_keywords = ["unique", "distinct", "different", "unique values of", "distinct values of", "which unique", "how many and which", "konse", "kaunse"]
            for kw in uniq_keywords:
                if kw in q_clean:
                    for col in cols:
                        if col.lower() in q_clean:
                            return IntentResult(
                                intent=IntentType.UNIQUE,
                                confidence=0.90,
                                is_deterministic=True,
                                params={"column": col},
                                matched_patterns=["unique_col_match"],
                            )

            # Simple null check match
            null_keywords = ["null", "missing", "nan", "empty", "nulls", "missing values"]
            for kw in null_keywords:
                if kw in q_clean:
                    for col in cols:
                        if col.lower() in q_clean:
                            return IntentResult(
                                intent=IntentType.NULL_CHECK,
                                confidence=0.85,
                                is_deterministic=True,
                                params={"column": col},
                                matched_patterns=["null_check_col_match"],
                            )

            # Simple count / frequency check (e.g. "how many Operating System")
            count_keywords = ["count of", "number of", "how many"]
            for kw in count_keywords:
                if kw in q_clean:
                    for col in cols:
                        if col.lower() in q_clean:
                            # If it's a categorical column, "how many <categorical_col>" means groupby + count (value counts)
                            if self.schema_index.is_categorical(col) or not self.schema_index.is_numeric(col):
                                return IntentResult(
                                    intent=IntentType.GROUP_BY,
                                    confidence=0.90,
                                    is_deterministic=True,
                                    params={"column": col, "groupby": col},
                                    matched_patterns=["groupby_categorical_count"],
                                )
                            else:
                                # For numeric or other columns, it means count of entries
                                return IntentResult(
                                    intent=IntentType.COUNT_ROWS,
                                    confidence=0.90,
                                    is_deterministic=True,
                                    params={"column": col},
                                    matched_patterns=["count_col_match"],
                                )

        # ─── 5. Ranking Match (Top/Bottom N by Column) ──────────────────────
        # e.g., "top 5 employees by salary", "lowest 10 products by sales"
        if self.schema_index:
            rank_match = re.search(
                r"\b(top|bottom|highest|lowest)\s*(\d+)?\s*(?:rows|records|records|lines|entries|items|employees|products|customers)?\s*(?:by|based on|sorted by)\s*([\w\s_]+)\b",
                q_clean
            )
            if rank_match:
                direction = rank_match.group(1)
                limit = int(rank_match.group(2)) if rank_match.group(2) else 5
                target_col_raw = rank_match.group(3).strip()
                
                # Resolve target column
                best = self.schema_index.best_match(target_col_raw)
                if best and best.confidence >= 0.80:
                    intent = IntentType.TOP_N if direction in ["top", "highest"] else IntentType.BOTTOM_N
                    return IntentResult(
                        intent=intent,
                        confidence=0.90,
                        is_deterministic=True,
                        params={"limit": limit, "column": best.matched_column},
                        matched_patterns=["rank_regex_match"],
                    )

        # Fallback: Let hybrid router decide
        return IntentResult(
            intent=IntentType.UNKNOWN,
            confidence=0.0,
            is_deterministic=False,
        )
