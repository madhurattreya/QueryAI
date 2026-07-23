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
        Dynamically detects dataset domain (Sports, Sales, HR, Finance, General) and builds relevant KPIs and charts.
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

        cols_lower = {c.lower(): c for c in df.columns}

        # ─── DOMAIN DETECTION ──────────────────────────────────────────────────
        is_sports = any(k in cols_lower for k in [
            "player_name", "jersey_number", "goals", "assists", "shots", "position",
            "stadium", "match_result", "tournament_rating", "fifa", "player_rating", "player_id"
        ])
        is_hr = any(k in cols_lower for k in [
            "employee", "employee_id", "salary", "designation", "hire_date", "performance_rating", "experience", "department"
        ])
        is_sales = any(k in cols_lower for k in [
            "sales", "revenue", "order_id", "profit", "orderdate", "unitprice", "discount"
        ])

        if is_sports:
            domain_type = "sports"
        elif is_hr:
            domain_type = "hr"
        elif is_sales:
            domain_type = "sales"
        else:
            domain_type = "general"

        # ─── 1. SPORTS DOMAIN COMPUTATION ─────────────────────────────────────
        if domain_type == "sports":
            player_col = cols_lower.get("player_name") or cols_lower.get("player_id")
            team_col = cols_lower.get("team") or cols_lower.get("nationality") or cols_lower.get("club_name") or cols_lower.get("country")
            position_col = cols_lower.get("position")
            goals_col = cols_lower.get("goals") or cols_lower.get("total_goals_tournament") or cols_lower.get("points") or cols_lower.get("score")
            rating_col = cols_lower.get("player_rating") or cols_lower.get("tournament_rating") or cols_lower.get("performance_score")
            stage_col = cols_lower.get("tournament_stage") or cols_lower.get("match_date") or cols_lower.get("city") or cols_lower.get("stadium")

            tot_records = int(len(df))
            tot_goals = int(pd.to_numeric(df[goals_col], errors="coerce").sum()) if goals_col else 0
            avg_rating = round(float(pd.to_numeric(df[rating_col], errors="coerce").mean()), 2) if rating_col else 0.0
            tot_teams = int(df[team_col].nunique()) if team_col else 0

            # Chart 1: Goals by Team
            team_dict = {}
            if team_col and goals_col:
                try:
                    gdf = df.groupby(team_col)[goals_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum()).nlargest(6)
                    team_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}
                except Exception:
                    pass

            # Chart 2: Position Distribution
            position_dict = {}
            if position_col:
                try:
                    position_dict = {str(k): int(v) for k, v in df[position_col].value_counts().items()}
                except Exception:
                    pass

            # Chart 3: Top 5 Goal Scorers
            entity_dict = {}
            if player_col and goals_col:
                try:
                    gdf = df.groupby(player_col)[goals_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum()).nlargest(5)
                    entity_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}
                except Exception:
                    pass

            # Chart 4: Stage/Date Trend
            stage_dict = {}
            if stage_col and goals_col:
                try:
                    gdf = df.groupby(stage_col)[goals_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum()).nlargest(12)
                    stage_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}
                except Exception:
                    pass

            return {
                "status": "success",
                "domain_type": "sports",
                "dataset_name": ds_name,
                "dashboard_title": "FIFA World Cup Player Performance Analytics",
                "unit_symbol": "",
                "total_rows": tot_records,
                "kpis": {
                    "card1_title": "Total Player Records",
                    "card1_val": f"{tot_records:,}",
                    "card1_badge": "Players",
                    "card2_title": "Total Tournament Goals",
                    "card2_val": f"{tot_goals:,}",
                    "card2_badge": "Goals Scored",
                    "card3_title": "Avg Player Rating",
                    "card3_val": f"{avg_rating:.2f}",
                    "card3_badge": "Rating / 10",
                    "card4_title": "Participating Teams",
                    "card4_val": f"{tot_teams}",
                    "card4_badge": "Teams / Nations"
                },
                "titles": {
                    "region": "Total Goals by National Team",
                    "category": "Player Position Breakdown",
                    "entity": "Top 5 Goal Scorers"
                },
                "charts": {
                    "regional": team_dict,
                    "category": position_dict,
                    "salespersons": entity_dict,
                    "monthly": stage_dict
                }
            }

        # ─── 2. SALES DOMAIN COMPUTATION ─────────────────────────────────────
        elif domain_type == "sales":
            sales_col = cols_lower.get("sales") or cols_lower.get("revenue") or cols_lower.get("total_sales") or cols_lower.get("amount")
            profit_col = cols_lower.get("profit") or cols_lower.get("margin") or cols_lower.get("discount")
            region_col = cols_lower.get("region") or cols_lower.get("area") or cols_lower.get("zone") or cols_lower.get("state")
            category_col = cols_lower.get("category") or cols_lower.get("product_category") or cols_lower.get("segment")
            entity_col = cols_lower.get("salesperson") or cols_lower.get("sales_rep") or cols_lower.get("employee") or cols_lower.get("customer") or cols_lower.get("product")
            date_col = cols_lower.get("month") or cols_lower.get("orderdate") or cols_lower.get("date")

            tot_sales = float(pd.to_numeric(df[sales_col], errors="coerce").sum()) if sales_col else 0.0
            tot_profit = float(pd.to_numeric(df[profit_col], errors="coerce").sum()) if profit_col else 0.0
            tot_orders = int(len(df))
            avg_val = float(tot_sales / tot_orders) if tot_orders > 0 else 0.0

            region_dict = {}
            if region_col and sales_col:
                gdf = df.groupby(region_col)[sales_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
                region_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}

            category_dict = {}
            if category_col and sales_col:
                gdf = df.groupby(category_col)[sales_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
                category_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}

            entity_dict = {}
            if entity_col and sales_col:
                gdf = df.groupby(entity_col)[sales_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum()).nlargest(5)
                entity_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}

            monthly_dict = {}
            if date_col and sales_col:
                gdf = df.groupby(date_col)[sales_col].apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
                monthly_dict = {str(k): float(v) for k, v in gdf.items() if pd.notnull(v)}

            return {
                "status": "success",
                "domain_type": "sales",
                "dataset_name": ds_name,
                "dashboard_title": "Sales & Commercial Performance Dashboard",
                "unit_symbol": "$",
                "total_rows": tot_orders,
                "kpis": {
                    "card1_title": "Total Revenue",
                    "card1_val": f"${tot_sales:,.2f}",
                    "card1_badge": "Revenue",
                    "card2_title": "Total Profit",
                    "card2_val": f"${tot_profit:,.2f}",
                    "card2_badge": "Profit",
                    "card3_title": "Total Orders",
                    "card3_val": f"{tot_orders:,}",
                    "card3_badge": "Orders",
                    "card4_title": "Avg Order Value",
                    "card4_val": f"${avg_val:,.2f}",
                    "card4_badge": "Avg / Order"
                },
                "titles": {
                    "region": f"{region_col or 'Region'} Sales Performance",
                    "category": f"{category_col or 'Category'} Revenue Breakdown",
                    "entity": f"Top 5 Performing {entity_col or 'Salespersons'}s"
                },
                "charts": {
                    "regional": region_dict,
                    "category": category_dict,
                    "salespersons": entity_dict,
                    "monthly": monthly_dict
                }
            }

        # ─── 3. GENERAL / HR / OTHER FALLBACK ─────────────────────────────────
        else:
            num_cols = df.select_dtypes(include=["number"]).columns.tolist()
            text_cols = df.select_dtypes(include=["object", "category", "string"]).columns.tolist()
            
            m1 = num_cols[0] if num_cols else None
            m2 = num_cols[1] if len(num_cols) > 1 else m1
            c1 = text_cols[0] if text_cols else "Group"
            c2 = text_cols[1] if len(text_cols) > 1 else c1
            c3 = text_cols[2] if len(text_cols) > 2 else c1

            v1 = float(pd.to_numeric(df[m1], errors="coerce").sum()) if m1 else 0.0
            v2 = float(pd.to_numeric(df[m2], errors="coerce").mean()) if m2 else 0.0
            tot_r = int(len(df))
            u_cat = int(df[c1].nunique()) if c1 in df else 0

            d1 = df.groupby(c1)[m1].sum().nlargest(6).to_dict() if c1 in df and m1 else {}
            d2 = df.groupby(c2).size().to_dict() if c2 in df else {}
            d3 = df.groupby(c3)[m1].sum().nlargest(5).to_dict() if c3 in df and m1 else {}

            return {
                "status": "success",
                "domain_type": "general",
                "dataset_name": ds_name,
                "dashboard_title": f"{ds_name.replace('_', ' ').title()} Analytics Overview",
                "unit_symbol": "",
                "total_rows": tot_r,
                "kpis": {
                    "card1_title": "Total Records",
                    "card1_val": f"{tot_r:,}",
                    "card1_badge": "Rows",
                    "card2_title": f"Total {m1 or 'Metric'}",
                    "card2_val": f"{v1:,.2f}",
                    "card2_badge": m1 or "Sum",
                    "card3_title": f"Avg {m2 or 'Metric'}",
                    "card3_val": f"{v2:,.2f}",
                    "card3_badge": m2 or "Mean",
                    "card4_title": f"Unique {c1}",
                    "card4_val": f"{u_cat:,}",
                    "card4_badge": "Unique"
                },
                "titles": {
                    "region": f"{m1 or 'Metric'} by {c1}",
                    "category": f"{c2} Distribution",
                    "entity": f"Top 5 {c3}s"
                },
                "charts": {
                    "regional": d1,
                    "category": d2,
                    "salespersons": d3,
                    "monthly": {}
                }
            }

