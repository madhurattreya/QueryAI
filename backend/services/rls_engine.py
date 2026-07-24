"""
backend/services/rls_engine.py
───────────────────────────────
Row-Level Security (RLS) & PII Data Masking Engine.

Applies fine-grained user data governance:
1. Dynamic Row-Level Filtering (e.g. injects `WHERE region = 'West'` based on user session context)
2. Column-Level PII Obfuscation (masks sensitive fields like Email, SSN, Credit Card numbers for non-admin roles)
"""

from __future__ import annotations
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

logger = logging.getLogger("queryiq.rls")

# Default sensitive column patterns for PII detection
PII_PATTERNS = [
    r"email", r"ssn", r"social_security", r"credit_card", r"card_num",
    r"phone", r"mobile", r"password", r"secret", r"birth_date", r"dob"
]

class RLSEngine:
    """
    Enterprise Row-Level Security & Data Masking Engine.
    """

    def apply_rls_to_dataframe(
        self,
        df: pd.DataFrame,
        user_context: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        Applies row-level predicate filtering and column masking to a Pandas DataFrame.
        """
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return df

        res_df = df.copy()
        role = user_context.get("role", "viewer").lower()
        user_attributes = user_context.get("attributes", {})

        # 1. Row-Level Security Filtering
        # Example: user_attributes = {"region": "West", "department": "Sales"}
        for attr_key, attr_val in user_attributes.items():
            # Find matching column in DataFrame (case-insensitive)
            matching_cols = [c for c in res_df.columns if c.lower() == attr_key.lower()]
            if matching_cols:
                col = matching_cols[0]
                if isinstance(attr_val, list):
                    res_df = res_df[res_df[col].isin(attr_val)]
                else:
                    res_df = res_df[res_df[col] == attr_val]

        # 2. PII Column Masking for non-admin roles
        if role not in ["admin", "superadmin", "owner"]:
            res_df = self.mask_pii_columns(res_df)

        return res_df

    def mask_pii_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Masks values in columns that match sensitive PII patterns.
        """
        masked_df = df.copy()
        for col in masked_df.columns:
            col_lower = col.lower()
            if any(re.search(pat, col_lower) for pat in PII_PATTERNS):
                # Mask string values
                if pd.api.types.is_string_dtype(masked_df[col]) or masked_df[col].dtype == object:
                    masked_df[col] = masked_df[col].astype(str).apply(self._mask_val)
        return masked_df

    def apply_rls_to_sql_query(
        self,
        sql: str,
        user_context: Dict[str, Any]
    ) -> str:
        """
        Applies SQL predicate injection for database query isolation.
        """
        user_attributes = user_context.get("attributes", {})
        if not user_attributes or not sql:
            return sql

        where_clauses = []
        for attr_key, attr_val in user_attributes.items():
            if isinstance(attr_val, str):
                where_clauses.append(f"{attr_key} = '{attr_val}'")
            elif isinstance(attr_val, (int, float)):
                where_clauses.append(f"{attr_key} = {attr_val}")
            elif isinstance(attr_val, list):
                val_list = ", ".join([f"'{v}'" if isinstance(v, str) else str(v) for v in attr_val])
                where_clauses.append(f"{attr_key} IN ({val_list})")

        if not where_clauses:
            return sql

        clause_str = " AND ".join(where_clauses)
        if "WHERE" in sql.upper():
            return re.sub(r"(?i)\bWHERE\b", f"WHERE {clause_str} AND ", sql, count=1)
        else:
            return f"{sql} WHERE {clause_str}"

    def _mask_val(self, val: str) -> str:
        if not val or val == "nan" or val == "None":
            return val
        if "@" in val:
            parts = val.split("@")
            return parts[0][0] + "***@" + parts[1]
        if len(val) > 4:
            return val[:2] + "*" * (len(val) - 4) + val[-2:]
        return "***"


# Global singleton instance
rls_engine = RLSEngine()
