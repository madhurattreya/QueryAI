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
        Modifies an existing dashboard layout based on natural language commands.
        """
        dash = self.db_manager.get_dashboard(dash_id)
        if not dash:
            raise ValueError("Dashboard not found")

        prompt = DASHBOARD_EDIT_PROMPT.format(existing_layout=json.dumps(dash["layout"]), question=question)
        model = config.settings.get("model", "qwen2.5:7b")
        try:
            raw_response, _ = self.llm_manager.call_llm_with_fallback(prompt, model, 0.0)
            clean_str = raw_response.strip().strip("`").replace("json\n", "").strip()
            layout = json.loads(clean_str)
            self.db_manager.update_dashboard(dash_id, title=layout.get("title"), layout=layout)
            return layout
        except Exception:
            return dash["layout"]
