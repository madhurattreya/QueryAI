import json
import backend.config as config
from backend.services.llm import LLMManager
from backend.services.dashboard_manager import DashboardManager

DASHBOARD_PROMPT = """
You are an expert Enterprise BI Architect.
Based on the user request, generate a structured dashboard layout configuration in JSON format.
The output MUST be a valid JSON object only (do not include markdown code block syntax or explanation).

The JSON structure should be:
{{
  "title": "Dashboard Title",
  "cards": [
    {{
      "id": "card_uuid",
      "type": "kpi or chart",
      "title": "Card Title",
      "w": 3,
      "h": 2,
      "x": 0,
      "y": 0,
      "query": "The natural language query or measure used to fetch the data",
      "chart_type": "bar or line or pie or scatter or none"
    }}
  ]
}}

User request:
{question}

Available Columns / Schema:
{schema}
"""

DASHBOARD_EDIT_PROMPT = """
You are an expert Enterprise BI Architect.
You need to modify the existing dashboard layout based on the user's editing request.
The output MUST be a valid JSON object matching the updated dashboard layout.

Existing Dashboard Layout:
{existing_layout}

User editing request:
{question}
"""

import re
import uuid

def extract_json_payload(raw_response: str) -> dict:
    if not raw_response or not raw_response.strip():
        raise ValueError("Empty response received from LLM.")
    
    text = raw_response.strip()

    # 1. Direct JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Extract ```json ... ``` or ``` ... ``` block
    block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if block_match:
        try:
            data = json.loads(block_match.group(1).strip())
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Find first '{' and last '}'
    first_b = text.find("{")
    last_b = text.rfind("}")
    if first_b != -1 and last_b > first_b:
        try:
            data = json.loads(text[first_b:last_b + 1].strip())
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    raise ValueError(f"Could not parse valid JSON from LLM response: {text[:100]}")


class AIDashboardService:
    def __init__(self):
        self.db_manager = DashboardManager()
        self.llm_manager = LLMManager()

    def build_smart_dashboard(self, question: str, schema_desc: str) -> dict:
        """
        Constructs a smart, question-aware dashboard layout by inspecting user request.
        """
        q = question.lower()
        title = "Enterprise Analytics Dashboard"
        cards = []
        
        if "sales" in q:
            title = "Sales & Performance Dashboard"
        elif "financial" in q or "revenue" in q:
            title = "Financial Overview Dashboard"
        elif "executive" in q or "summary" in q:
            title = "Executive Performance Summary"

        # Default KPI cards
        cards.append({
            "id": str(uuid.uuid4()),
            "type": "kpi",
            "title": "Total Revenue",
            "w": 3, "h": 2, "x": 0, "y": 0,
            "query": "total sales",
            "chart_type": "none"
        })
        cards.append({
            "id": str(uuid.uuid4()),
            "type": "kpi",
            "title": "Total Profit",
            "w": 3, "h": 2, "x": 3, "y": 0,
            "query": "total profit",
            "chart_type": "none"
        })
        cards.append({
            "id": str(uuid.uuid4()),
            "type": "kpi",
            "title": "Total Orders",
            "w": 3, "h": 2, "x": 6, "y": 0,
            "query": "total orders",
            "chart_type": "none"
        })
        cards.append({
            "id": str(uuid.uuid4()),
            "type": "kpi",
            "title": "Avg Order Value",
            "w": 3, "h": 2, "x": 9, "y": 0,
            "query": "average order value",
            "chart_type": "none"
        })

        current_y = 2

        # Requested chart cards
        if "regional" in q or "region" in q or "sales bar" in q:
            cards.append({
                "id": str(uuid.uuid4()),
                "type": "chart",
                "title": "Regional Sales Performance",
                "w": 6, "h": 3, "x": 0, "y": current_y,
                "query": "show total sales by region",
                "chart_type": "bar"
            })
            
        if "category" in q or "revenue pie" in q or "pie chart" in q:
            cards.append({
                "id": str(uuid.uuid4()),
                "type": "chart",
                "title": "Category Revenue Breakdown",
                "w": 6, "h": 3, "x": 6 if any(c["title"] == "Regional Sales Performance" for c in cards) else 0, "y": current_y,
                "query": "show total revenue by category",
                "chart_type": "pie"
            })

        if any(c["y"] == current_y for c in cards if c["type"] == "chart"):
            current_y += 3

        if "monthly" in q or "trend" in q or "line chart" in q:
            cards.append({
                "id": str(uuid.uuid4()),
                "type": "chart",
                "title": "Monthly Sales Trend",
                "w": 8, "h": 4, "x": 0, "y": current_y,
                "query": "show monthly sales trend",
                "chart_type": "line"
            })

        if "top" in q or "salesperson" in q or "top 5" in q:
            cards.append({
                "id": str(uuid.uuid4()),
                "type": "chart",
                "title": "Top 5 Performing Salespersons",
                "w": 4, "h": 4, "x": 8 if any(c["title"] == "Monthly Sales Trend" for c in cards) else 0, "y": current_y,
                "query": "show top 5 salespersons by sales",
                "chart_type": "bar"
            })

        return {
            "title": title,
            "cards": cards
        }

    def generate_dashboard(self, question: str, schema_desc: str) -> dict:
        """
        Uses LLM or smart question-aware builder to generate dashboard layout configuration.
        Provides sub-second response for structured dashboard requests.
        """
        q = question.lower()
        is_structured_req = any(k in q for k in ["regional", "category", "pie", "line", "top 5", "salespersons", "bar chart", "trend", "complete sales dashboard"])

        layout = None
        if not is_structured_req:
            try:
                prompt = DASHBOARD_PROMPT.format(question=question, schema=schema_desc)
                model = config.settings.get("model", config.app_settings.default_model)
                raw_response, _, _llm_metrics = self.llm_manager.call_llm_with_fallback(prompt, model, 0.0)
                layout = extract_json_payload(raw_response)
            except Exception as e:
                print(f"[DASHBOARD GEN WARNING] LLM JSON parsing failed: {e}. Falling back to smart dashboard builder.")

        if not layout or not isinstance(layout, dict):
            layout = self.build_smart_dashboard(question, schema_desc)

        # Sanitize cards to guarantee typed dict elements
        title = str(layout.get("title") or "Sales & Business Dashboard")
        cards = layout.get("cards", [])
        clean_cards = []
        if isinstance(cards, list):
            for idx, c in enumerate(cards):
                if isinstance(c, dict):
                    clean_cards.append({
                        "id": str(c.get("id") or f"c_{idx}"),
                        "type": str(c.get("type") or "chart"),
                        "title": str(c.get("title") or f"Metric {idx+1}"),
                        "w": int(c.get("w", 4)),
                        "h": int(c.get("h", 3)),
                        "x": int(c.get("x", (idx * 4) % 12)),
                        "y": int(c.get("y", (idx * 4) // 12 * 3)),
                        "query": str(c.get("query") or question),
                        "chart_type": str(c.get("chart_type") or "bar")
                    })

        if not clean_cards:
            smart_fallback = self.build_smart_dashboard(question, schema_desc)
            clean_cards = smart_fallback["cards"]
            title = smart_fallback["title"]

        final_layout = {"title": title, "cards": clean_cards}
        dash_id = self.db_manager.create_dashboard(title, final_layout)
        final_layout["id"] = dash_id
        return final_layout

    def edit_dashboard(self, dash_id: str, question: str) -> dict:
        """
        Modifies an existing dashboard layout based on natural language commands deterministically.
        """
        import re
        dash = self.db_manager.get_dashboard(dash_id)
        if not dash:
            raise ValueError("Dashboard not found")

        layout = dash["layout"]
        if not layout:
            layout = {"title": "Dashboard", "cards": []}
        
        cards = layout.get("cards", [])
        q = question.lower().strip()

        # Helper to find card by title or query substring
        def find_card(name_query):
            nq = name_query.lower().strip()
            # Try exact title
            for c in cards:
                if c.get("title", "").lower() == nq:
                    return c
            # Try substring title
            for c in cards:
                if nq in c.get("title", "").lower():
                    return c
            # Try substring query
            for c in cards:
                if nq in c.get("query", "").lower():
                    return c
            return None

        modified = False

        # 1. Rename: "rename [x] to [y]"
        rename_match = re.search(r"rename\s+(.+?)\s+to\s+(.+)", q)
        if rename_match:
            target = rename_match.group(1).strip()
            new_name = rename_match.group(2).strip().title()
            c = find_card(target)
            if c:
                c["title"] = new_name
                modified = True

        # 2. Change/Replace chart type: "replace [x] with [type]" or "change [x] to [type]"
        chart_match = re.search(r"(?:replace|change|convert)\s+(.+?)\s+(?:with|to)\s+(pie|bar|line|scatter|kpi|chart)", q)
        if chart_match:
            target = chart_match.group(1).strip()
            new_type = chart_match.group(2).strip()
            c = find_card(target)
            if c:
                if new_type == "kpi":
                    c["type"] = "kpi"
                    c["chart_type"] = "none"
                else:
                    c["type"] = "chart"
                    c["chart_type"] = new_type
                modified = True

        # 3. Delete/Remove: "delete [x]" or "remove [x]"
        delete_match = re.search(r"(?:delete|remove)\s+(.+)", q)
        if delete_match and not modified:
            target = delete_match.group(1).strip()
            c = find_card(target)
            if c:
                cards = [card for card in cards if card["id"] != c["id"]]
                layout["cards"] = cards
                modified = True

        # 4. Duplicate: "duplicate [x]"
        dup_match = re.search(r"duplicate\s+(.+)", q)
        if dup_match:
            target = dup_match.group(1).strip()
            c = find_card(target)
            if c:
                import uuid
                new_card = c.copy()
                new_card["id"] = str(uuid.uuid4())
                new_card["title"] = f"Copy of {c['title']}"
                new_card["x"] = (c.get("x", 0) + 2) % 12
                new_card["y"] = c.get("y", 0) + 2
                cards.append(new_card)
                modified = True

        # 5. Move: "move [x] to [top/bottom]" or "move [x] [left/right/up/down]"
        move_match = re.search(r"move\s+(.+?)\s+(?:to\s+)?(top|bottom|left|right|up|down)", q)
        if move_match:
            target = move_match.group(1).strip()
            dir_pos = move_match.group(2).strip()
            c = find_card(target)
            if c:
                if dir_pos == "top":
                    c["y"] = 0
                elif dir_pos == "bottom":
                    c["y"] = max([x.get("y", 0) for x in cards]) + 2
                elif dir_pos == "left":
                    c["x"] = max(0, c.get("x", 0) - 2)
                elif dir_pos == "right":
                    c["x"] = min(10, c.get("x", 0) + 2)
                elif dir_pos == "up":
                    c["y"] = max(0, c.get("y", 0) - 2)
                elif dir_pos == "down":
                    c["y"] = c.get("y", 0) + 2
                modified = True

        # 6. Size increase/decrease: "increase [x] size" or "increase size of [x]" or "make [x] bigger"
        size_inc = re.search(r"(?:increase|make\s+bigger|expand)\s+(?:size\s+of\s+)?(.+)", q)
        if size_inc and not modified:
            target = size_inc.group(1).strip()
            c = find_card(target)
            if c:
                c["w"] = min(12, c.get("w", 3) + 2)
                c["h"] = c.get("h", 2) + 1
                modified = True

        # 7. Stack vertically: "stack charts vertically" or "stack vertically"
        if "stack" in q and "vertical" in q:
            current_y = 0
            for c in cards:
                c["x"] = 0
                c["w"] = 12
                c["y"] = current_y
                current_y += c.get("h", 2)
            modified = True

        # 8. Add card: "add [x]" (e.g. "add top customers")
        add_match = re.search(r"add\s+(.+)", q)
        if add_match and not modified:
            new_title = add_match.group(1).strip().title()
            import uuid
            new_card = {
                "id": str(uuid.uuid4()),
                "type": "chart" if "chart" in q or "sales" in q or "profit" in q else "kpi",
                "title": new_title,
                "w": 4 if "chart" in q else 3,
                "h": 3 if "chart" in q else 2,
                "x": 0,
                "y": max([x.get("y", 0) + x.get("h", 2) for x in cards]) if cards else 0,
                "query": new_title.lower(),
                "chart_type": "bar" if "chart" in q else "none"
            }
            cards.append(new_card)
            modified = True

        # 9. Change color palette: "change color palette to [palette]"
        palette_match = re.search(r"palette\s+(?:to\s+)?([a-z0-9]+)", q)
        if palette_match:
            layout["color_palette"] = palette_match.group(1)
            modified = True

        if modified:
            self.db_manager.update_dashboard(dash_id, title=layout.get("title"), layout=layout)

        return layout

    def compute_live_dashboard_data(self, layout: dict = None) -> dict:
        """
        Calculates 100% real live metric aggregations and chart group data directly from the active loaded dataset.
        """
        import pandas as pd
        from backend.services.dataset_manager import DatasetManager
        
        if not config.datasets:
            DatasetManager().load_active_dataset_on_startup()
            
        if not config.datasets:
            return {"status": "empty", "message": "No active dataset loaded"}
            
        ds_name = list(config.datasets.keys())[0]
        df = config.datasets[ds_name]
        if df is None or df.empty:
            return {"status": "empty", "dataset_name": ds_name}
            
        # Detect numeric and categorical columns dynamically
        cols = {c.lower(): c for c in df.columns}
        
        sales_col = cols.get("sales") or cols.get("revenue") or cols.get("total_sales") or cols.get("amount")
        profit_col = cols.get("profit") or cols.get("margin")
        region_col = cols.get("region") or cols.get("area") or cols.get("zone") or cols.get("state")
        category_col = cols.get("category") or cols.get("product_category") or cols.get("segment") or cols.get("type")
        salesperson_col = cols.get("salesperson") or cols.get("sales_rep") or cols.get("employee") or cols.get("agent")
        month_col = cols.get("month") or cols.get("orderdate") or cols.get("date")

        # 1. Compute KPIs
        tot_sales = float(pd.to_numeric(df[sales_col], errors="coerce").sum()) if sales_col else 0.0
        tot_profit = float(pd.to_numeric(df[profit_col], errors="coerce").sum()) if profit_col else 0.0
        tot_orders = int(len(df))
        avg_val = float(tot_sales / tot_orders) if tot_orders > 0 else 0.0

        # 2. Compute Regional Breakdown
        region_dict = {}
        if region_col and sales_col:
            try:
                gdf = df.groupby(region_col)[sales_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
                region_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}
            except Exception:
                pass

        # 3. Compute Category Breakdown
        category_dict = {}
        if category_col and sales_col:
            try:
                gdf = df.groupby(category_col)[sales_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
                category_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}
            except Exception:
                pass

        # 4. Compute Top 5 Salespersons Breakdown
        salesperson_dict = {}
        if salesperson_col and sales_col:
            try:
                gdf = df.groupby(salesperson_col)[sales_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum()).nlargest(5)
                salesperson_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}
            except Exception:
                pass

        # 5. Compute Monthly Trend Breakdown
        monthly_dict = {}
        if month_col and sales_col:
            try:
                gdf = df.groupby(month_col)[sales_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
                monthly_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}
            except Exception:
                pass

        return {
            "status": "success",
            "dataset_name": ds_name,
            "total_rows": tot_orders,
            "kpis": {
                "total_revenue": round(tot_sales, 2),
                "total_profit": round(tot_profit, 2),
                "total_orders": tot_orders,
                "avg_order_value": round(avg_val, 2)
            },
            "charts": {
                "regional": region_dict,
                "category": category_dict,
                "salespersons": salesperson_dict,
                "monthly": monthly_dict
            }
        }

