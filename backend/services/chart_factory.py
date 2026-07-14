import os
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

def build_bar_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    return px.bar(df, x=x, y=y, title=title, template="plotly_dark")

def build_line_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    return px.line(df, x=x, y=y, title=title, template="plotly_dark")

def build_scatter_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    return px.scatter(df, x=x, y=y, title=title, template="plotly_dark")

def build_box_plot(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    return px.box(df, x=x, y=y, title=title, template="plotly_dark")

def build_histogram(df: pd.DataFrame, x: str, title: str) -> go.Figure:
    return px.histogram(df, x=x, title=title, template="plotly_dark")

def build_pie_chart(df: pd.DataFrame, x: str, y: str = None, title: str = "") -> go.Figure:
    return px.pie(df, names=x, values=y, title=title, template="plotly_dark")

def build_heatmap(df: pd.DataFrame, x: list = None, y: list = None, title: str = "") -> go.Figure:
    # Correlation Matrix
    numeric_df = df.select_dtypes(include=["number"])
    corr = numeric_df.corr()
    fig = px.imshow(corr, x=corr.columns, y=corr.columns, title=title, template="plotly_dark")
    return fig

def build_area_chart(df: pd.DataFrame, x: str, y: str, title: str) -> go.Figure:
    return px.area(df, x=x, y=y, title=title, template="plotly_dark")

def build_treemap(df: pd.DataFrame, path: list, values: str = None, title: str = "") -> go.Figure:
    return px.treemap(df, path=path, values=values, title=title, template="plotly_dark")

def create_chart_assets(fig: go.Figure, charts_dir: str, chart_uuid: str) -> str:
    """
    Saves the interactive Plotly HTML and serializes the figure object to JSON.
    Does NOT call Kaleido.
    Returns result string.
    """
    os.makedirs(charts_dir, exist_ok=True)
    html_path = os.path.join(charts_dir, f"{chart_uuid}.html")
    json_path = os.path.join(charts_dir, f"{chart_uuid}.json")
    
    # Save interactive HTML
    fig.write_html(html_path, include_plotlyjs="cdn")
    
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
