"""
backend/services/validation_layer.py
──────────────────────────────────────
Pre-execution query and code validation layer.
Validates code structure, columns, types, and security constraints before execution.
Integrates AST parsing for Python and basic parser for SQL.
"""
from __future__ import annotations
import ast
import re
from typing import Dict, List, Optional, Set, Tuple
import backend.config as config
from backend.models.execution_plan import ValidationError, ValidationResult, ValidationSeverity
from backend.services.column_resolver import ColumnResolver
from backend.services.schema_index import SchemaIndex, SchemaIndexRegistry


class CodeVisitor(ast.NodeVisitor):
    """AST visitor to extract accessed dataframe column names and check for unsafe nodes."""

    def __init__(self, df_aliases: Set[str], available_cols: Set[str]):
        self.df_aliases = df_aliases
        self.available_cols = available_cols
        self.accessed_cols: Set[str] = set()
        self.unsafe_calls: List[str] = []

    def visit_Subscript(self, node: ast.Subscript):
        # Match df['col_name'] or df[['col1', 'col2']]
        if isinstance(node.value, ast.Name) and node.value.id in self.df_aliases:
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                self.accessed_cols.add(node.slice.value)
            elif isinstance(node.slice, ast.Index) and isinstance(node.slice.value, ast.Constant) and isinstance(node.slice.value, str):
                # Python < 3.9 compat
                self.accessed_cols.add(node.slice.value)
            elif isinstance(node.slice, ast.List):
                for elt in node.slice.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        self.accessed_cols.add(elt.value)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Match df.col_name
        if isinstance(node.value, ast.Name) and node.value.id in self.df_aliases:
            # Exclude built-in pandas attributes like head, tail, sum, groupby, columns, index, etc.
            pandas_builtins = {
                "head", "tail", "groupby", "sum", "mean", "count", "min", "max",
                "median", "std", "var", "columns", "index", "dtypes", "iloc", "loc",
                "drop", "merge", "join", "nlargest", "nsmallest", "describe", "shape",
                "copy", "astype", "dropna", "fillna", "sort_values", "reset_index"
            }
            if node.attr not in pandas_builtins:
                self.accessed_cols.add(node.attr)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Detect unsafe function calls
        if isinstance(node.func, ast.Name):
            if node.func.id in ["eval", "exec", "open", "compile", "__import__"]:
                self.unsafe_calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in ["eval", "system", "popen", "spawn", "subprocess"]:
                self.unsafe_calls.append(node.func.attr)
        self.generic_visit(node)


class ValidationLayer:
    """
    Validates executed code and query parameters prior to sandboxed run.
    Catches syntax errors, column hallucinations, and unsafe operations.
    """

    def __init__(self, dataset_name: Optional[str] = None):
        self.dataset_name = dataset_name
        self.schema_index = SchemaIndexRegistry.get(dataset_name) if dataset_name else None
        self.resolver = ColumnResolver(self.schema_index) if self.schema_index else None

    def validate_python_code(self, code: str) -> ValidationResult:
        """
        Parses generated python code into an AST. Checks columns and safety.
        """
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        # 1. Parse AST
        try:
            tree = ast.parse(code)
        except SyntaxError as se:
            errors.append(ValidationError(
                code="SYNTAX_ERROR",
                message=f"Python code has syntax error: {se.msg} (line {se.lineno})",
                severity=ValidationSeverity.ERROR
            ))
            return ValidationResult(passed=False, errors=errors)

        # 2. Setup environment aliases for search
        df_aliases = {"df", "result"}
        if self.dataset_name:
            df_aliases.add(self.dataset_name)
            df_aliases.add(self.dataset_name.replace(" ", "_").lower())
            
        available_cols = set(self.schema_index.get_all_columns()) if self.schema_index else set()

        # 3. Walk tree to gather accesses
        visitor = CodeVisitor(df_aliases, available_cols)
        visitor.visit(tree)

        # 4. Check unsafe operations
        if visitor.unsafe_calls:
            for call in visitor.unsafe_calls:
                errors.append(ValidationError(
                    code="SECURITY_VIOLATION",
                    message=f"Blocked unsafe call '{call}' in code sandbox.",
                    severity=ValidationSeverity.ERROR
                ))

        # 5. Check columns referenced
        if self.schema_index and self.resolver:
            for accessed_col in visitor.accessed_cols:
                # Direct check
                if not self.schema_index.column_exists(accessed_col):
                    # Try recovery
                    res = self.resolver.resolve(accessed_col)
                    if res.is_resolved:
                        warnings.append(ValidationError(
                            code="COLUMN_RESOLVED_WITH_FUZZY",
                            message=f"Column '{accessed_col}' not found; resolved to '{res.resolved_column}' via {res.strategy_used.value}.",
                            severity=ValidationSeverity.WARNING,
                            column=accessed_col,
                            suggestion=res.resolved_column
                        ))
                    else:
                        errors.append(ValidationError(
                            code="COLUMN_NOT_FOUND",
                            message=f"Column '{accessed_col}' does not exist in dataset schema.",
                            severity=ValidationSeverity.ERROR,
                            column=accessed_col,
                            suggestion=self.schema_index.get_all_columns()[0] if self.schema_index.get_all_columns() else None
                        ))

        passed = len(errors) == 0
        return ValidationResult(passed=passed, errors=errors, warnings=warnings)

    def validate_sql_query(self, sql: str) -> ValidationResult:
        """
        Validates SQL query against DDL injection, safety, and column references.
        """
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []
        sql_clean = sql.upper().strip()

        # 1. Block DDL / write operations
        blocked_keywords = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE INTO", "TRUNCATE"]
        for kw in blocked_keywords:
            if re.search(fr"\b{kw}\b", sql_clean):
                errors.append(ValidationError(
                    code="SECURITY_VIOLATION",
                    message=f"Write operations are blocked. Found SQL command: {kw}",
                    severity=ValidationSeverity.ERROR
                ))

        # 2. Extract column references via regex (approximate validation for SQL)
        if self.schema_index and self.resolver:
            # Match SELECT ... FROM columns, WHERE columns, GROUP BY columns
            all_cols = self.schema_index.get_all_columns()
            
            # Simple keyword word scanner
            sql_words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", sql)
            # Filter sql language keywords
            sql_keywords = {
                "SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "LIMIT", "OFFSET", "AND", "OR",
                "IN", "LIKE", "IS", "NULL", "AS", "ON", "JOIN", "INNER", "LEFT", "OUTER", "CROSS",
                "SUM", "AVG", "COUNT", "MAX", "MIN", "MEAN", "HAVING", "CASE", "WHEN", "THEN", "ELSE",
                "END", "DENSE_RANK", "OVER", "PARTITION", "ASC", "DESC"
            }
            
            suspected_cols = [w for w in sql_words if w.upper() not in sql_keywords and not w.isdigit()]
            for s_col in suspected_cols:
                # If word has matching pattern with columns but casing/spaces differ
                # We skip table name if it matches active dataset
                if self.dataset_name and s_col.lower() == self.dataset_name.lower():
                    continue
                # If word exists as column name exactly, or lowercase matches table schema
                if not self.schema_index.column_exists(s_col):
                    # Check if it resembles any of the actual columns (Levenshtein threshold)
                    res = self.resolver.resolve(s_col)
                    if res.is_resolved:
                        # If highly confident, warn
                        if res.confidence >= 0.85:
                            warnings.append(ValidationError(
                                code="COLUMN_RESOLVED_WITH_FUZZY",
                                message=f"SQL identifier '{s_col}' resolved to schema column '{res.resolved_column}'.",
                                severity=ValidationSeverity.WARNING,
                                column=s_col,
                                suggestion=res.resolved_column
                            ))
                    else:
                        # Don't throw hard error for SQL identifier fallback unless we are 100% sure it's a hallucinated col
                        # Standard SQL might contain table aliases, SQL variables, functions, etc.
                        pass

        passed = len(errors) == 0
        return ValidationResult(passed=passed, errors=errors, warnings=warnings)
