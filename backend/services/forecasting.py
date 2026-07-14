import pandas as pd
import numpy as np

class ForecastingService:
    def forecast_linear_trend(self, df: pd.DataFrame, date_col: str, value_col: str, periods: int = 3, freq: str = 'ME') -> pd.DataFrame:
        """
        Calculates a linear trend projection.
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
        
        # Calculate residuals and confidence intervals
        residuals = y - (slope * x + intercept)
        std_error = np.std(residuals) if len(residuals) > 0 else 0.0
        
        forecast_df = pd.DataFrame({
            date_col: future_dates,
            value_col: future_y,
            "Lower_CI": future_y - 1.96 * std_error,
            "Upper_CI": future_y + 1.96 * std_error,
            "Type": "Forecast"
        })
        
        grouped['Type'] = 'Actual'
        grouped['Lower_CI'] = grouped[value_col]
        grouped['Upper_CI'] = grouped[value_col]
        
        return pd.concat([grouped, forecast_df], ignore_index=True)

    def forecast_exponential_smoothing(self, df: pd.DataFrame, date_col: str, value_col: str, periods: int = 3, freq: str = 'ME', alpha: float = 0.3) -> pd.DataFrame:
        """
        Performs Simple Exponential Smoothing forecast.
        """
        temp_df = df.copy()
        temp_df[date_col] = pd.to_datetime(temp_df[date_col], errors='coerce')
        temp_df = temp_df.dropna(subset=[date_col])
        
        grouped = temp_df.groupby(pd.Grouper(key=date_col, freq=freq))[value_col].sum().reset_index()
        if len(grouped) < 2:
            return pd.DataFrame()
            
        y = grouped[value_col].values
        s = np.zeros(len(y))
        s[0] = y[0]
        
        for t in range(1, len(y)):
            s[t] = alpha * y[t] + (1 - alpha) * s[t-1]
            
        # The forecast for all future periods is the last smoothed value
        last_val = s[-1]
        
        last_date = grouped[date_col].max()
        future_dates = pd.date_range(start=last_date, periods=periods + 1, freq=freq)[1:]
        future_y = np.full(periods, last_val)
        
        # Calculate residuals std dev
        residuals = y - s
        std_error = np.std(residuals) if len(residuals) > 0 else 0.0
        
        forecast_df = pd.DataFrame({
            date_col: future_dates,
            value_col: future_y,
            "Lower_CI": future_y - 1.96 * std_error,
            "Upper_CI": future_y + 1.96 * std_error,
            "Type": "Forecast"
        })
        
        grouped['Type'] = 'Actual'
        grouped['Lower_CI'] = grouped[value_col]
        grouped['Upper_CI'] = grouped[value_col]
        
        return pd.concat([grouped, forecast_df], ignore_index=True)

    def scenario_what_if(self, df: pd.DataFrame, target_col: str, increase_pct: float) -> pd.DataFrame:
        """
        Runs scenario "What If" analysis adjusting the target metric.
        """
        df_copy = df.copy()
        if target_col in df_copy.columns:
            df_copy[f"{target_col}_Adjusted"] = df_copy[target_col] * (1.0 + increase_pct / 100.0)
        return df_copy
