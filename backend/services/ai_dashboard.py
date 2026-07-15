import json
import backend.config as config
from backend.services.llm import LLMManager
from backend.services.dashboard_manager import DashboardManager

DASHBOARD_PROMPT = """
You are an expert Enterprise BI Architect.
Based on the user request, generate a structured dashboard layout configuration in JSON format.
The output MUST be a valid JSON object only (do not include markdown code block syntax or explanation).

The JSON structure should be:
{
  "title": "Dashboard Title",
  "cards": [
    {
      "id": "card_uuid",
      "type": "kpi" or "chart",
      "title": "Card Title",
      "w": 3,  // width (1 to 12 grid)
      "h": 2,  // height units
      "x": 0,  // x position
      "y": 0,  // y position
      "query": "The natural language query or measure used to fetch the data",
      "chart_type": "bar" or "line" or "pie" or "scatter" or "none"
    }
  ]
}

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

class AIDashboardService:
    def __init__(self):
        self.db_manager = DashboardManager()
        self.llm_manager = LLMManager()

    def generate_dashboard(self, question: str, schema_desc: str) -> dict:
        """
        Uses LLM to generate a complete dashboard layout configuration.
        """
        prompt = DASHBOARD_PROMPT.format(question=question, schema=schema_desc)
        model = config.settings.get("model", "qwen2.5:7b")
        try:
            raw_response, _ = self.llm_manager.call_llm_with_fallback(prompt, model, 0.0)
            
            # Clean response of backticks
            clean_str = raw_response.strip().strip("`").replace("json\n", "").strip()
            # If still has markdown backticks, strip them
            if clean_str.startswith("```"):
                clean_str = clean_str.split("```")[1].strip()
                
            layout = json.loads(clean_str)
            
            # Persist to database
            dash_id = self.db_manager.create_dashboard(layout.get("title", "New AI Dashboard"), layout)
            layout["id"] = dash_id
            return layout
        except Exception as e:
            # Fallback layout
            fallback = {
                "title": "Executive Summary",
                "cards": [
                    {"id": "c1", "type": "kpi", "title": "Total Revenue", "w": 4, "h": 2, "x": 0, "y": 0, "query": "total sales", "chart_type": "none"},
                    {"id": "c2", "type": "kpi", "title": "Total Profit", "w": 4, "h": 2, "x": 4, "y": 0, "query": "total profit", "chart_type": "none"},
                    {"id": "c3", "type": "chart", "title": "Sales by City", "w": 8, "h": 4, "x": 0, "y": 2, "query": "sales by city", "chart_type": "bar"}
                ]
            }
            dash_id = self.db_manager.create_dashboard("Executive Summary", fallback)
            fallback["id"] = dash_id
            return fallback

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
