import pandas as pd
import numpy as np

def calculate_running_total(df: pd.DataFrame, value_col: str, group_cols: list = None) -> pd.Series:
    """
    Calculates cumulative sum of a column, optionally grouped.
    """
    if group_cols:
        return df.groupby(group_cols)[value_col].cumsum()
    return df[value_col].cumsum()

def calculate_moving_average(df: pd.DataFrame, value_col: str, window: int = 3, group_cols: list = None) -> pd.Series:
    """
    Calculates rolling window moving average, optionally grouped.
    """
    if group_cols:
        return df.groupby(group_cols)[value_col].transform(lambda x: x.rolling(window, min_periods=1).mean())
    return df[value_col].rolling(window, min_periods=1).mean()

def calculate_cagr(start_val: float, end_val: float, periods: float) -> float:
    """
    Calculates Compound Annual Growth Rate.
    """
    if start_val <= 0 or end_val <= 0 or periods <= 0:
        return 0.0
    return float((end_val / start_val) ** (1.0 / periods) - 1.0)

def calculate_growth_rate(df: pd.DataFrame, date_col: str, value_col: str, period: str = 'YoY') -> pd.DataFrame:
    """
    Aggregates value_col by date_col and calculates period-over-period percentage change.
    period can be 'YoY', 'QoQ', or 'MoM'.
    """
    temp_df = df.copy()
    temp_df[date_col] = pd.to_datetime(temp_df[date_col], errors='coerce')
    temp_df = temp_df.dropna(subset=[date_col])
    
    if period == 'YoY':
        freq = 'YE'
    elif period == 'QoQ':
        freq = 'QE'
    else:
        freq = 'ME'
        
    grouped = temp_df.groupby(pd.Grouper(key=date_col, freq=freq))[value_col].sum().reset_index()
    grouped['Growth'] = grouped[value_col].pct_change()
    return grouped

def calculate_rank(df: pd.DataFrame, value_col: str, group_cols: list = None, method: str = 'dense', ascending: bool = False) -> pd.Series:
    """
    Assigns ranks to records.
    """
    if group_cols:
        return df.groupby(group_cols)[value_col].rank(method=method, ascending=ascending)
    return df[value_col].rank(method=method, ascending=ascending)

def detect_anomalies(df: pd.DataFrame, value_col: str, method: str = 'iqr') -> pd.Series:
    """
    Performs outlier detection using IQR or Z-score method.
    """
    series = df[value_col]
    if method == 'iqr':
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        return (series < lower_bound) | (series > upper_bound)
    else:
        mean = series.mean()
        std = series.std()
        if std == 0:
            return pd.Series(False, index=df.index)
        z_scores = (series - mean) / std
        return z_scores.abs() > 3

def calculate_pareto(df: pd.DataFrame, entity_col: str, value_col: str) -> pd.DataFrame:
    """
    Applies Pareto 80/20 rule classification.
    """
    grouped = df.groupby(entity_col)[value_col].sum().reset_index()
    grouped = grouped.sort_values(by=value_col, ascending=False).reset_index(drop=True)
    total = grouped[value_col].sum()
    if total == 0:
        grouped['Cumulative_Pct'] = 0.0
        grouped['In_Top_80'] = False
        return grouped
        
    grouped['Cumulative_Pct'] = grouped[value_col].cumsum() / total
    grouped['In_Top_80'] = grouped['Cumulative_Pct'] <= 0.80
    
    # Include the element that actually cross 80% boundary
    cross_mask = grouped['Cumulative_Pct'] > 0.80
    if cross_mask.any():
        cross_idx = cross_mask.idxmax()
        grouped.loc[:cross_idx, 'In_Top_80'] = True
    return grouped

def calculate_abc_classification(df: pd.DataFrame, entity_col: str, value_col: str) -> pd.DataFrame:
    """
    Performs ABC Inventory/Customer classification based on accumulated values:
    A: top 70%, B: next 20%, C: bottom 10%.
    """
    grouped = df.groupby(entity_col)[value_col].sum().reset_index()
    grouped = grouped.sort_values(by=value_col, ascending=False).reset_index(drop=True)
    total = grouped[value_col].sum()
    if total == 0:
        grouped['ABC_Class'] = 'C'
        return grouped
        
    grouped['Cumulative_Pct'] = grouped[value_col].cumsum() / total
    
    def classify(pct):
        if pct <= 0.70:
            return 'A'
        elif pct <= 0.90:
            return 'B'
        else:
            return 'C'
            
    grouped['ABC_Class'] = grouped['Cumulative_Pct'].apply(classify)
    return grouped

def simple_forecast(df: pd.DataFrame, date_col: str, value_col: str, periods: int = 3, freq: str = 'ME') -> pd.DataFrame:
    """
    Performs linear regression-based forecast projection.
    """
    temp_df = df.copy()
    temp_df[date_col] = pd.to_datetime(temp_df[date_col], errors='coerce')
    temp_df = temp_df.dropna(subset=[date_col])
    
    grouped = temp_df.groupby(pd.Grouper(key=date_col, freq=freq))[value_col].sum().reset_index()
    if len(grouped) < 2:
        return pd.DataFrame()
        
    x = np.arange(len(grouped))
    y = grouped[value_col].values
    slope, intercept = np.polyfit(x, y, 1)
    
    last_date = grouped[date_col].max()
    future_dates = pd.date_range(start=last_date, periods=periods + 1, freq=freq)[1:]
    
    future_x = np.arange(len(grouped), len(grouped) + periods)
    future_y = slope * future_x + intercept
    
    forecast_df = pd.DataFrame({
        date_col: future_dates,
        value_col: future_y,
        "Type": "Forecast"
    })
    
    grouped['Type'] = 'Actual'
    return pd.concat([grouped, forecast_df], ignore_index=True)
