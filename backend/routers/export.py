from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
import io
import json
import pandas as pd
from backend.services.dashboard_manager import DashboardManager
import backend.config as config

router = APIRouter(prefix="/api/export")

from fastapi.concurrency import run_in_threadpool

@router.get("/dashboard/excel/{id}")
async def export_dashboard_excel(id: str):
    def generate_excel():
        db_manager = DashboardManager()
        dash = db_manager.get_dashboard(id)
        if not dash:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        cards = dash["layout"].get("cards", [])
        
        # Write to memory stream
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # 1. Dashboard summary sheet
            summary_data = []
            for c in cards:
                summary_data.append({
                    "Card Title": c.get("title"),
                    "Type": c.get("type"),
                    "Query": c.get("query"),
                    "Width": c.get("w"),
                    "Height": c.get("h")
                })
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name="Dashboard Summary", index=False)
            
            # 2. Add sheet for each card if it has matching loaded datasets
            active_df_name = None
            for name in config.datasets.keys():
                active_df_name = name
                break
                
            if active_df_name:
                df = config.datasets[active_df_name]
                for idx, c in enumerate(cards[:4]): # limit to 4 sheets to prevent huge payloads
                    sheet_name = f"Card {idx + 1}"
                    # Just export first 100 rows of active dataset for demo card
                    df.head(100).to_excel(writer, sheet_name=sheet_name[:30], index=False)
                    
        output.seek(0)
        return output, dash["title"]

    try:
        output, title = await run_in_threadpool(generate_excel)
        filename = f"{title.replace(' ', '_')}_Export.xlsx"
        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
        return StreamingResponse(
            output,
            headers=headers,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/pdf/{id}", response_class=HTMLResponse)
def export_dashboard_pdf(id: str):
    """
    Returns a printable HTML/CSS version of the dashboard that users can print or save as PDF.
    """
    try:
        db_manager = DashboardManager()
        dash = db_manager.get_dashboard(id)
        if not dash:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        title = dash.get("title", "AI Dashboard")
        cards = dash["layout"].get("cards", [])
        
        # Build a beautiful, responsive HTML grid of cards for printing
        cards_html = ""
        for c in cards:
            bg_color = "bg-white"
            type_badge = f"<span style='font-size: 10px; background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-weight: bold;'>{c.get('type').upper()}</span>"
            cards_html += f"""
            <div style="background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); page-break-inside: avoid;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <h3 style="margin: 0; font-size: 14px; color: #012060; font-weight: bold;">{c.get('title')}</h3>
                    {type_badge}
                </div>
                <div style="font-size: 12px; color: #4a5568; font-style: italic; margin-bottom: 20px;">
                    Query: "{c.get('query')}"
                </div>
                <div style="height: 120px; border: 1px dashed #cbd5e0; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #a0aec0; font-size: 11px;">
                    [ {c.get('chart_type').upper() if c.get('chart_type') != 'none' else 'KPI VALUE'} VISUALIZATION CONTAINER ]
                </div>
            </div>
            """
            
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{title}</title>
            <style>
                body {{
                    font-family: 'Helvetica Neue', Arial, sans-serif;
                    background: #f7fafc;
                    margin: 0;
                    padding: 40px;
                    color: #2d3748;
                }}
                .header {{
                    border-bottom: 2px solid #012060;
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .title {{
                    font-size: 24px;
                    color: #012060;
                    margin: 0;
                    font-weight: bold;
                }}
                .grid {{
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 20px;
                }}
                @media print {{
                    body {{
                        background: white;
                        padding: 0;
                    }}
                    .no-print {{
                        display: none;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div>
                    <h1 class="title">{title}</h1>
                    <div style="font-size: 12px; color: #718096; margin-top: 5px;">Generated by QueryIQ Enterprise Analytics</div>
                </div>
                <button class="no-print" onclick="window.print()" style="background: #012060; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; cursor: pointer;">
                    Print / Save PDF
                </button>
            </div>
            <div class="grid">
                {cards_html}
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
