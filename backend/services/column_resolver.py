"""
backend/services/column_resolver.py
────────────────────────────────────
Multi-stage column name recovery pipeline.
Tries 8 distinct strategies in order:
  1. Exact Match
  2. Case-Insensitive Match
  3. Whitespace Normalization (strip, collapse internal spaces)
  4. Underscore Normalization (spaces ↔ underscores)
  5. Levenshtein Distance (using standard library difflib or rapidfuzz)
  6. Token Sort Ratio (difflib/sequence matcher sequence)
  7. Semantic Similarity (stubbed, configurable via .env)
  8. LLM Hint (fallback error generation)

Records every step taken in a resolution_steps log to aid telemetry.
"""
from __future__ import annotations
import difflib
import time
from typing import Dict, List, Optional, Tuple

import backend.config as config
from backend.models.execution_plan import ColumnResolutionResult, ResolutionStep, ResolutionStrategy
from backend.services.schema_index import SchemaIndex, SchemaIndexRegistry


class ColumnResolver:
    """
    Resolves misspelled, partial, or semantic column names to the actual dataset columns.
    Records tracing information for transparency.
    """

    def __init__(self, schema_index: SchemaIndex):
        self.schema_index = schema_index
        self.columns = schema_index.get_all_columns()

    def resolve(self, query_column: str) -> ColumnResolutionResult:
        """
        Runs the 8-step column recovery pipeline on the input query string.
        """
        t_start_total = time.time()
        steps: List[ResolutionStep] = []
        original = query_column.strip()

        # Step 1: Exact Match
        t_start = time.time()
        if original in self.columns:
            step = ResolutionStep(
                step=1,
                strategy=ResolutionStrategy.EXACT,
                query=original,
                result=original,
                confidence=1.0,
                elapsed_ms=(time.time() - t_start) * 1000,
            )
            steps.append(step)
            return ColumnResolutionResult(
                original_query=original,
                resolved_column=original,
                confidence=1.0,
                strategy_used=ResolutionStrategy.EXACT,
                steps=steps,
                is_resolved=True,
            )
        steps.append(ResolutionStep(1, ResolutionStrategy.EXACT, original, None, 0.0, (time.time() - t_start) * 1000))

        # Step 2: Case-Insensitive Match
        t_start = time.time()
        lower_orig = original.lower()
        matched = next((c for c in self.columns if c.lower() == lower_orig), None)
        if matched:
            step = ResolutionStep(
                step=2,
                strategy=ResolutionStrategy.CASE_INSENSITIVE,
                query=original,
                result=matched,
                confidence=0.98,
                elapsed_ms=(time.time() - t_start) * 1000,
            )
            steps.append(step)
            return ColumnResolutionResult(
                original_query=original,
                resolved_column=matched,
                confidence=0.98,
                strategy_used=ResolutionStrategy.CASE_INSENSITIVE,
                steps=steps,
                is_resolved=True,
            )
        steps.append(ResolutionStep(2, ResolutionStrategy.CASE_INSENSITIVE, original, None, 0.0, (time.time() - t_start) * 1000))

        # Step 3: Whitespace Normalization
        t_start = time.time()
        norm_orig = " ".join(lower_orig.split())
        matched = next((c for c in self.columns if " ".join(c.lower().split()) == norm_orig), None)
        if matched:
            step = ResolutionStep(
                step=3,
                strategy=ResolutionStrategy.WHITESPACE_NORMALIZED,
                query=original,
                result=matched,
                confidence=0.95,
                elapsed_ms=(time.time() - t_start) * 1000,
            )
            steps.append(step)
            return ColumnResolutionResult(
                original_query=original,
                resolved_column=matched,
                confidence=0.95,
                strategy_used=ResolutionStrategy.WHITESPACE_NORMALIZED,
                steps=steps,
                is_resolved=True,
            )
        steps.append(ResolutionStep(3, ResolutionStrategy.WHITESPACE_NORMALIZED, original, None, 0.0, (time.time() - t_start) * 1000))

        # Step 4: Underscore Normalization
        t_start = time.time()
        flat_orig = norm_orig.replace("_", " ").replace("-", " ")
        matched = next((c for c in self.columns if c.lower().replace("_", " ").replace("-", " ") == flat_orig), None)
        if matched:
            step = ResolutionStep(
                step=4,
                strategy=ResolutionStrategy.UNDERSCORE_NORMALIZED,
                query=original,
                result=matched,
                confidence=0.92,
                elapsed_ms=(time.time() - t_start) * 1000,
            )
            steps.append(step)
            return ColumnResolutionResult(
                original_query=original,
                resolved_column=matched,
                confidence=0.92,
                strategy_used=ResolutionStrategy.UNDERSCORE_NORMALIZED,
                steps=steps,
                is_resolved=True,
            )
        steps.append(ResolutionStep(4, ResolutionStrategy.UNDERSCORE_NORMALIZED, original, None, 0.0, (time.time() - t_start) * 1000))

        # Step 5: Levenshtein Distance (using difflib/close matches fallback)
        t_start = time.time()
        close_matches = difflib.get_close_matches(original, self.columns, n=1, cutoff=0.70)
        if not close_matches:
            # try lowercase matching
            close_matches = difflib.get_close_matches(lower_orig, [c.lower() for c in self.columns], n=1, cutoff=0.70)
            if close_matches:
                matched = next((c for c in self.columns if c.lower() == close_matches[0]), None)
            else:
                matched = None
        else:
            matched = close_matches[0]

        if matched:
            step = ResolutionStep(
                step=5,
                strategy=ResolutionStrategy.LEVENSHTEIN,
                query=original,
                result=matched,
                confidence=0.85,
                elapsed_ms=(time.time() - t_start) * 1000,
            )
            steps.append(step)
            return ColumnResolutionResult(
                original_query=original,
                resolved_column=matched,
                confidence=0.85,
                strategy_used=ResolutionStrategy.LEVENSHTEIN,
                steps=steps,
                is_resolved=True,
            )
        steps.append(ResolutionStep(5, ResolutionStrategy.LEVENSHTEIN, original, None, 0.0, (time.time() - t_start) * 1000))

        # Step 6: Token Sort Ratio / SequenceMatcher Token Similarity
        t_start = time.time()
        best_ratio = 0.0
        best_col = None
        for col in self.columns:
            # Heuristic sort ratio: sort words of both query and column, compare sequence match
            q_words = sorted(flat_orig.split())
            c_words = sorted(col.lower().replace("_", " ").replace("-", " ").split())
            ratio = difflib.SequenceMatcher(None, q_words, c_words).ratio()
            if ratio > best_ratio and ratio >= 0.60:
                best_ratio = ratio
                best_col = col

        if best_col:
            step = ResolutionStep(
                step=6,
                strategy=ResolutionStrategy.RAPIDFUZZ_TOKEN_SORT,
                query=original,
                result=best_col,
                confidence=round(0.60 + (best_ratio * 0.25), 2),
                elapsed_ms=(time.time() - t_start) * 1000,
            )
            steps.append(step)
            return ColumnResolutionResult(
                original_query=original,
                resolved_column=best_col,
                confidence=round(0.60 + (best_ratio * 0.25), 2),
                strategy_used=ResolutionStrategy.RAPIDFUZZ_TOKEN_SORT,
                steps=steps,
                is_resolved=True,
            )
        steps.append(ResolutionStep(6, ResolutionStrategy.RAPIDFUZZ_TOKEN_SORT, original, None, 0.0, (time.time() - t_start) * 1000))

        # Step 7: Semantic Similarity (Disabled by default, returns warning/not found)
        t_start = time.time()
        steps.append(ResolutionStep(7, ResolutionStrategy.SEMANTIC, original, None, 0.0, (time.time() - t_start) * 1000))

        # Step 8: LLM Hint (We generate the formatted missing column error message)
        t_start = time.time()
        error_msg = f"ERROR: Column '{original}' does not exist in dataset. Did you mean one of: {self.columns[:5]}?"
        step = ResolutionStep(
            step=8,
            strategy=ResolutionStrategy.LLM_HINT,
            query=original,
            result=error_msg,
            confidence=0.10,
            elapsed_ms=(time.time() - t_start) * 1000,
        )
        steps.append(step)

        return ColumnResolutionResult(
            original_query=original,
            resolved_column=None,
            confidence=0.0,
            strategy_used=ResolutionStrategy.NOT_FOUND,
            steps=steps,
            is_resolved=False,
        )
