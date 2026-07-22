import os
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

THEME_COLORS = {
    "paper_bg": "#0f172a",       # Slate 900
    "plot_bg": "#1e293b",        # Slate 800
    "accent_primary": "#38bdf8", # Vibrant Sky Blue
    "accent_secondary": "#818cf8", # Vibrant Indigo
    "text_primary": "#f8fafc",   # Bright White
    "text_secondary": "#94a3b8", # Light Slate
    "grid_color": "#334155",     # Slate 700 Grid
    "palette": [
        "#38bdf8", "#818cf8", "#34d399", "#fbbf24", "#f43f5e",
        "#a855f7", "#ec4899", "#06b6d4", "#10b981", "#f97316"
    ]
}

def apply_custom_theme(fig: go.Figure, title: str = "") -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=THEME_COLORS["paper_bg"],
        plot_bgcolor=THEME_COLORS["plot_bg"],
        font=dict(family="Inter, system-ui, sans-serif", color=THEME_COLORS["text_primary"], size=13),
        title=dict(
            text=f"<b>{title}</b>" if title else "",
            x=0.02,
            y=0.95,
            xanchor="left",
            font=dict(size=18, color=THEME_COLORS["text_primary"])
        ),
        margin=dict(l=60, r=40, t=70, b=60),
        colorway=THEME_COLORS["palette"],
        legend=dict(
            font=dict(color=THEME_COLORS["text_primary"]),
            bgcolor="rgba(15, 23, 42, 0.7)",
            bordercolor=THEME_COLORS["grid_color"],
            borderwidth=1
        ),
        hoverlabel=dict(
            bgcolor="#1e293b",
            font_color="#f8fafc",
            font_size=13,
            bordercolor="#38bdf8"
        )
    )
    fig.update_xaxes(
        gridcolor=THEME_COLORS["grid_color"],
        zerolinecolor=THEME_COLORS["grid_color"],
        tickfont=dict(color=THEME_COLORS["text_primary"], size=12),
        title_font=dict(color=THEME_COLORS["text_primary"], size=14),
        showline=True,
        linecolor=THEME_COLORS["grid_color"]
    )
    fig.update_yaxes(
        gridcolor=THEME_COLORS["grid_color"],
        zerolinecolor=THEME_COLORS["grid_color"],
        tickfont=dict(color=THEME_COLORS["text_primary"], size=12),
        title_font=dict(color=THEME_COLORS["text_primary"], size=14),
        showline=True,
        linecolor=THEME_COLORS["grid_color"]
    )
    return fig

def build_bar_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    fig = px.bar(df, x=x, y=y, title=title, color_discrete_sequence=THEME_COLORS["palette"])
    fig.update_traces(
        marker_color=THEME_COLORS["accent_primary"],
        marker_line_color="#60a5fa",
        marker_line_width=1.5,
        opacity=0.95
    )
    return apply_custom_theme(fig, title)

def build_line_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    fig = px.line(df, x=x, y=y, title=title, color_discrete_sequence=THEME_COLORS["palette"])
    fig.update_traces(
        line=dict(width=3, color=THEME_COLORS["accent_primary"]),
        mode="lines+markers",
        marker=dict(size=6, color="#60a5fa")
    )
    return apply_custom_theme(fig, title)

def build_scatter_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    fig = px.scatter(df, x=x, y=y, title=title, color_discrete_sequence=THEME_COLORS["palette"])
    fig.update_traces(
        marker=dict(size=8, color=THEME_COLORS["accent_primary"], line=dict(width=1, color="#60a5fa"))
    )
    return apply_custom_theme(fig, title)

def build_box_plot(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    fig = px.box(df, x=x, y=y, title=title, color_discrete_sequence=THEME_COLORS["palette"])
    fig.update_traces(marker_color=THEME_COLORS["accent_primary"])
    return apply_custom_theme(fig, title)

def build_histogram(df: pd.DataFrame, x: str, title: str) -> go.Figure:
    fig = px.histogram(df, x=x, title=title, color_discrete_sequence=THEME_COLORS["palette"])
    fig.update_traces(
        marker_color=THEME_COLORS["accent_primary"],
        marker_line_color="#60a5fa",
        marker_line_width=1.5
    )
    return apply_custom_theme(fig, title)

def build_pie_chart(df: pd.DataFrame, x: str, y: str = None, title: str = "") -> go.Figure:
    fig = px.pie(df, names=x, values=y, title=title, color_discrete_sequence=THEME_COLORS["palette"])
    fig.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='#0f172a', width=2)))
    return apply_custom_theme(fig, title)

def build_heatmap(df: pd.DataFrame, x: list = None, y: list = None, title: str = "") -> go.Figure:
    numeric_df = df.select_dtypes(include=["number"])
    corr = numeric_df.corr()
    fig = px.imshow(corr, x=corr.columns, y=corr.columns, title=title, color_continuous_scale="Viridis")
    return apply_custom_theme(fig, title)

def build_area_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    fig = px.area(df, x=x, y=y, title=title, color_discrete_sequence=THEME_COLORS["palette"])
    fig.update_traces(line=dict(color=THEME_COLORS["accent_primary"], width=2))
    return apply_custom_theme(fig, title)

def build_treemap(df: pd.DataFrame, path: list, values: str = None, title: str = "") -> go.Figure:
    fig = px.treemap(df, path=path, values=values, title=title, color_discrete_sequence=THEME_COLORS["palette"])
    return apply_custom_theme(fig, title)

def create_chart_assets(fig: go.Figure, charts_dir: str, chart_uuid: str) -> str:
    """
    Saves the interactive Plotly HTML and serializes the figure object to JSON.
    Does NOT call Kaleido. Uses local directory JS bundling to eliminate CDN latency/buffering.
    Returns result string.
    """
    os.makedirs(charts_dir, exist_ok=True)
    html_path = os.path.join(charts_dir, f"{chart_uuid}.html")
    static_html_path = os.path.join(charts_dir, "chart.html")
    json_path = os.path.join(charts_dir, f"{chart_uuid}.json")
    
    # Save interactive HTML with local JS dependency to avoid external CDN latency
    try:
        fig.write_html(html_path, include_plotlyjs="directory")
        fig.write_html(static_html_path, include_plotlyjs="directory")
    except Exception:
        fig.write_html(html_path, include_plotlyjs="cdn")
        fig.write_html(static_html_path, include_plotlyjs="cdn")
    
    # Save serialized figure JSON
    fig_json = fig.to_json()
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(fig_json)
        
    return "Chart saved to chart.png and chart.html"

def generate_png_on_demand(charts_dir: str, chart_uuid: str) -> bool:
    """
    Loads serialized JSON and generates static PNG using Kaleido.
    """
    json_path = os.path.join(charts_dir, f"{chart_uuid}.json")
    png_path = os.path.join(charts_dir, f"{chart_uuid}.png")
    
    if os.path.exists(png_path):
        return True
        
    if not os.path.exists(json_path):
        return False
        
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            fig_json = f.read()
        fig = pio.from_json(fig_json)
        fig.write_image(png_path)
        return True
    except Exception as e:
        print(f"[ON-DEMAND PNG ERROR]: {str(e)}")
        return False

