from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from backend.services.schema_index import SchemaIndex, SemanticType

class BaseMetricFormula:
    def __init__(self, column: str, operator: str, display_name: str, expression: Optional[str] = None):
        self.column = column
        self.operator = operator          # "sum", "mean" (avg), "count", "nunique" (distinct count), "min", "max", "expression"
        self.display_name = display_name
        self.expression = expression      # for derived metrics e.g. "SUM(revenue) - SUM(cost)"

    def __repr__(self) -> str:
        return f"BaseMetricFormula(col={self.column}, op={self.operator}, expr={self.expression})"


class MetricCatalog:
    def __init__(self, schema_index: SchemaIndex):
        self.schema_index = schema_index
        self.catalog: Dict[str, BaseMetricFormula] = {}
        self._build_catalog()

    def _build_catalog(self) -> None:
        cols = self.schema_index.get_all_columns()
        
        # 1. Map columns dynamically based on their semantic types
        for col in cols:
            col_lower = col.lower()
            sem_type = self.schema_index.get_column_semantic_type(col)
            
            # Map standard prefixes for measures
            if sem_type == SemanticType.MEASURE:
                # Base column
                self.catalog[col_lower] = BaseMetricFormula(col, "sum", f"Total {col}")
                self.catalog[f"total {col_lower}"] = BaseMetricFormula(col, "sum", f"Total {col}")
                self.catalog[f"sum of {col_lower}"] = BaseMetricFormula(col, "sum", f"Total {col}")
                self.catalog[f"average {col_lower}"] = BaseMetricFormula(col, "mean", f"Average {col}")
                self.catalog[f"avg {col_lower}"] = BaseMetricFormula(col, "mean", f"Average {col}")
                self.catalog[f"mean of {col_lower}"] = BaseMetricFormula(col, "mean", f"Average {col}")
                self.catalog[f"max {col_lower}"] = BaseMetricFormula(col, "max", f"Max {col}")
                self.catalog[f"maximum {col_lower}"] = BaseMetricFormula(col, "max", f"Max {col}")
                self.catalog[f"min {col_lower}"] = BaseMetricFormula(col, "min", f"Min {col}")
                self.catalog[f"minimum {col_lower}"] = BaseMetricFormula(col, "min", f"Min {col}")
                
            elif sem_type == SemanticType.IDENTIFIER:
                # Clean identifier base name, e.g. "order_id" -> "order"
                base_word = re.sub(r"(_id|id|_code|code|_no|no|_number|number|_key|key|_uuid|uuid|_ref|ref)$", "", col_lower).strip()
                if not base_word:
                    base_word = col_lower
                    
                # Default is COUNT for identifiers
                self.catalog[f"total {col_lower}"] = BaseMetricFormula(col, "count", f"Total {col}")
                self.catalog[f"count of {col_lower}"] = BaseMetricFormula(col, "count", f"Total {col}")
                
                # Check entity-specific distinct counts (e.g. customers, clients, employees)
                is_distinct_entity = any(w in base_word for w in ("customer", "client", "user", "visitor", "employee", "vendor", "supplier", "account", "student"))
                if is_distinct_entity:
                    op = "nunique"
                    disp = f"Unique {base_word.capitalize()}s"
                else:
                    op = "count"
                    disp = f"Total {base_word.capitalize()}s"
                    
                self.catalog[base_word] = BaseMetricFormula(col, op, disp)
                self.catalog[f"total {base_word}"] = BaseMetricFormula(col, op, disp)
                self.catalog[f"total {base_word}s"] = BaseMetricFormula(col, op, disp)
                self.catalog[f"count of {base_word}s"] = BaseMetricFormula(col, op, disp)
                self.catalog[f"number of {base_word}s"] = BaseMetricFormula(col, op, disp)
                self.catalog[f"unique {base_word}s"] = BaseMetricFormula(col, "nunique", f"Unique {base_word.capitalize()}s")
                self.catalog[f"distinct {base_word}s"] = BaseMetricFormula(col, "nunique", f"Unique {base_word.capitalize()}s")

        # 2. Map standard business metric synonyms dynamically to matching columns
        synonyms_map = {
            "revenue": ["revenue", "sales", "turnover", "income", "amount", "salesamt", "netsales", "gmv", "billing", "earnings"],
            "profit": ["profit", "earnings", "netprofit", "gain", "margin"],
            "orders": ["order_id", "orderid", "transaction_id", "txnid", "invoice#", "invoice_no"],
            "customers": ["customer_id", "customerid", "client_id", "clientid", "buyer_id", "buyer"]
        }
        
        # Find which columns in the dataset correspond to these synonym classes
        resolved_classes = {}
        for category, syn_list in synonyms_map.items():
            best_col = None
            for col in cols:
                col_clean = col.lower().replace("_", "").replace(" ", "").replace("-", "")
                if col_clean in syn_list or any(syn in col_clean for syn in syn_list):
                    best_col = col
                    break
            if best_col:
                resolved_classes[category] = best_col

        # Map dynamic class metrics
        if "revenue" in resolved_classes:
            rev_col = resolved_classes["revenue"]
            self.catalog["revenue"] = BaseMetricFormula(rev_col, "sum", "Total Revenue")
            self.catalog["total revenue"] = BaseMetricFormula(rev_col, "sum", "Total Revenue")
            self.catalog["sales"] = BaseMetricFormula(rev_col, "sum", "Total Revenue")
            self.catalog["total sales"] = BaseMetricFormula(rev_col, "sum", "Total Revenue")
            self.catalog["turnover"] = BaseMetricFormula(rev_col, "sum", "Total Revenue")
            self.catalog["average revenue"] = BaseMetricFormula(rev_col, "mean", "Average Revenue")
            self.catalog["average sales"] = BaseMetricFormula(rev_col, "mean", "Average Revenue")
            
        if "profit" in resolved_classes:
            prof_col = resolved_classes["profit"]
            self.catalog["profit"] = BaseMetricFormula(prof_col, "sum", "Total Profit")
            self.catalog["total profit"] = BaseMetricFormula(prof_col, "sum", "Total Profit")
            self.catalog["average profit"] = BaseMetricFormula(prof_col, "mean", "Average Profit")
            
        if "orders" in resolved_classes:
            ord_col = resolved_classes["orders"]
            self.catalog["orders"] = BaseMetricFormula(ord_col, "count", "Total Orders")
            self.catalog["total orders"] = BaseMetricFormula(ord_col, "count", "Total Orders")
            self.catalog["order count"] = BaseMetricFormula(ord_col, "count", "Total Orders")
            self.catalog["number of orders"] = BaseMetricFormula(ord_col, "count", "Total Orders")
            self.catalog["txn count"] = BaseMetricFormula(ord_col, "count", "Total Orders")
            
        if "customers" in resolved_classes:
            cust_col = resolved_classes["customers"]
            self.catalog["customers"] = BaseMetricFormula(cust_col, "nunique", "Total Customers")
            self.catalog["total customers"] = BaseMetricFormula(cust_col, "nunique", "Total Customers")
            self.catalog["customer count"] = BaseMetricFormula(cust_col, "nunique", "Total Customers")
            self.catalog["number of customers"] = BaseMetricFormula(cust_col, "nunique", "Total Customers")

        # 3. Add derived expressions/calculated measures
        if "revenue" in resolved_classes and "orders" in resolved_classes:
            rev_col = resolved_classes["revenue"]
            ord_col = resolved_classes["orders"]
            
            # Check if Average Order Value is already a column
            aov_col = next((c for c in cols if c.lower() in ("aov", "average order value", "average_order_value")), None)
            if aov_col:
                self.catalog["average order value"] = BaseMetricFormula(aov_col, "mean", "Average Order Value")
                self.catalog["aov"] = BaseMetricFormula(aov_col, "mean", "Average Order Value")
            else:
                self.catalog["average order value"] = BaseMetricFormula(
                    column=rev_col,
                    operator="expression",
                    display_name="Average Order Value",
                    expression=f"SUM({rev_col}) / COUNT({ord_col})"
                )
                self.catalog["aov"] = self.catalog["average order value"]

        if "revenue" in resolved_classes and "customers" in resolved_classes:
            rev_col = resolved_classes["revenue"]
            cust_col = resolved_classes["customers"]
            arpu_col = next((c for c in cols if c.lower() in ("arpu", "average revenue per user", "average_revenue_per_user")), None)
            if arpu_col:
                self.catalog["arpu"] = BaseMetricFormula(arpu_col, "mean", "ARPU")
            else:
                self.catalog["arpu"] = BaseMetricFormula(
                    column=rev_col,
                    operator="expression",
                    display_name="ARPU",
                    expression=f"SUM({rev_col}) / COUNT(DISTINCT {cust_col})"
                )

        if "revenue" in resolved_classes and "profit" in resolved_classes:
            rev_col = resolved_classes["revenue"]
            prof_col = resolved_classes["profit"]
            pm_formula = BaseMetricFormula(
                column=prof_col,
                operator="expression",
                display_name="Profit Margin",
                expression=f"SUM({prof_col}) / SUM({rev_col})"
            )
            self.catalog["profit margin"] = pm_formula
            self.catalog["profit margin (profit ÷ sales)"] = pm_formula
            self.catalog["profit ÷ sales"] = pm_formula
            self.catalog["profit / sales"] = pm_formula
            self.catalog["margin"] = pm_formula

        # 4. Merge semantic model custom calculations from SQLite Semantic Metadata Store
        try:
            from backend.services.semantic_model import SemanticModelManager
            import backend.services.history_db as db
            
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM datasets WHERE name = ? LIMIT 1", (self.schema_index.dataset_name,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                dataset_id = row["id"]
                custom_items = SemanticModelManager().get_model_items(dataset_id)
                for item in custom_items:
                    col_name = item["name"]
                    display_name = item.get("display_name") or col_name
                    expr = item.get("expression")
                    
                    if item.get("type") in ("calculated_measure", "measure") and expr:
                        if col_name in cols:
                            self.catalog[col_name.lower()] = BaseMetricFormula(col_name, "sum", display_name)
                        else:
                            self.catalog[col_name.lower()] = BaseMetricFormula(
                                column=col_name,
                                operator="expression",
                                display_name=display_name,
                                expression=expr
                            )
                        
                        # Add display name and synonyms
                        for syn in (item.get("synonyms") or "").split(","):
                            if syn.strip():
                                self.catalog[syn.strip().lower()] = self.catalog[col_name.lower()]
        except Exception as e:
            print(f"[METRIC CATALOG WARNING] Failed to load custom semantic database items: {e}")

    def resolve_metric(self, query_str: str) -> Optional[BaseMetricFormula]:
        """
        Looks up a metric from the query string.
        Clean the query first and look for exact/partial keys.
        """
        q = query_str.lower().strip()
        q_clean = re.sub(r"[^\w\s\+/\-\*]", "", q) # remove punctuation but keep operators
        
        # Exact match
        if q_clean in self.catalog:
            return self.catalog[q_clean]
            
        # Match longest key first to avoid substring collisions
        sorted_keys = sorted(self.catalog.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if re.search(r"\b" + re.escape(key) + r"\b", q_clean):
                return self.catalog[key]
                
        return None
