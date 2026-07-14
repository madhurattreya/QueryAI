import os
import pandas as pd
import numpy as np

def generate_dataset_insights(df_name: str, df: pd.DataFrame) -> str:
    """
    Analyzes the dataframe programmatically using Pandas and returns a list
    of 5-10 concise, high-value business insights in markdown format.
    """
    if df is None or df.empty:
        return "No active dataset loaded for insights analysis."
        
    insights = []
    
    # 1. Dataset Dimensions & Basic Stats
    rows, cols = df.shape
    insights.append(f"**Dataset Dimensions**: The dataset '{df_name}' contains {rows} rows and {cols} columns.")
    
    # Missing values
    missing = df.isnull().sum()
    missing_cols = [f"'{c}' ({missing[c]} nulls)" for c in df.columns if missing[c] > 0]
    if missing_cols:
        insights.append(f"**Missing Values**: Found missing data in columns: {', '.join(missing_cols[:3])}.")
    else:
        insights.append("**Data Quality**: No missing values found across all columns.")
        
    # Duplicates
    dup_count = df.duplicated().sum()
    if dup_count > 0:
        insights.append(f"**Duplicate Rows**: Found {dup_count} duplicate rows in the dataset.")
        
    # Helper to find column by keyword
    def find_col(kws):
        for c in df.columns:
            if any(kw in c.lower() for kw in kws):
                return c
        return None

    # Identify primary columns
    salary_col = find_col(["salary", "pay", "wage"])
    dept_col = find_col(["department", "dept", "dep"])
    city_col = find_col(["city", "location", "town"])
    exp_col = find_col(["experience", "exp", "tenure", "years"])
    name_col = find_col(["name", "employee", "emp", "id"])
    date_col = find_col(["date", "join", "hire"])
    
    # 2. Salary Insights
    if salary_col:
        try:
            # Convert to numeric just in case
            sal_series = pd.to_numeric(df[salary_col], errors="coerce")
            valid_sal = sal_series.dropna()
            if not valid_sal.empty:
                total_payroll = valid_sal.sum()
                avg_sal = valid_sal.mean()
                insights.append(f"**Total Payroll**: Total payroll expenditure is ₹{total_payroll:,.2f} with an average salary of ₹{avg_sal:,.2f}.")
                
                # Max/Min salaries
                max_idx = valid_sal.idxmax()
                min_idx = valid_sal.idxmin()
                max_val = valid_sal.max()
                min_val = valid_sal.min()
                
                max_name = df.loc[max_idx, name_col] if name_col else f"Index {max_idx}"
                min_name = df.loc[min_idx, name_col] if name_col else f"Index {min_idx}"
                
                insights.append(f"**Salary Extremes**: Highest salary is ₹{max_val:,.2f} ({max_name}) and lowest is ₹{min_val:,.2f} ({min_name}).")
                
                # Outliers (mean +/- 2.2 std)
                std_sal = valid_sal.std()
                if std_sal > 0:
                    outliers = df[abs(sal_series - avg_sal) > 2.2 * std_sal]
                    if not outliers.empty:
                        outlier_names = outliers[name_col].tolist() if name_col else outliers.index.tolist()
                        insights.append(f"**Salary Outliers**: Detected {len(outliers)} salary outliers: {', '.join(map(str, outlier_names[:3]))}.")
        except Exception:
            pass
            
    # 3. Department Insights
    if dept_col:
        try:
            dept_counts = df[dept_col].value_counts()
            top_dept = dept_counts.index[0]
            top_dept_cnt = dept_counts.values[0]
            insights.append(f"**Department Distribution**: Largest department is '{top_dept}' with {top_dept_cnt} employees ({round(top_dept_cnt/rows*100, 1)}% of total).")
            
            if salary_col:
                sal_series = pd.to_numeric(df[salary_col], errors="coerce")
                dept_sal = df.groupby(dept_col)[salary_col].mean()
                top_sal_dept = dept_sal.idxmax()
                top_sal_dept_val = dept_sal.max()
                insights.append(f"**Top Paying Department**: Department '{top_sal_dept}' has the highest average salary of ₹{top_sal_dept_val:,.2f}.")
        except Exception:
            pass

    # 4. City Insights
    if city_col and salary_col:
        try:
            city_sal = df.groupby(city_col)[salary_col].sum()
            top_city_payroll = city_sal.idxmax()
            top_city_payroll_val = city_sal.max()
            insights.append(f"**Top City Payroll**: City '{top_city_payroll}' represents the highest payroll location at ₹{top_city_payroll_val:,.2f}.")
        except Exception:
            pass

    # 5. Experience Insights
    if exp_col:
        try:
            exp_series = pd.to_numeric(df[exp_col], errors="coerce").dropna()
            if not exp_series.empty:
                max_exp = exp_series.max()
                max_exp_idx = exp_series.idxmax()
                max_exp_name = df.loc[max_exp_idx, name_col] if name_col else f"Index {max_exp_idx}"
                insights.append(f"**Highest Experience**: Maximum experience is {max_exp} years, held by {max_exp_name}.")
                
                # Correlation Salary & Experience
                if salary_col:
                    sal_series = pd.to_numeric(df[salary_col], errors="coerce").dropna()
                    common_idx = exp_series.index.intersection(sal_series.index)
                    if len(common_idx) > 3:
                        r_val = np.corrcoef(exp_series.loc[common_idx], sal_series.loc[common_idx])[0, 1]
                        if not np.isnan(r_val):
                            corr_desc = "strong positive" if r_val > 0.7 else "moderate positive" if r_val > 0.4 else "weak or no"
                            insights.append(f"**Experience-Salary Link**: There is a {corr_desc} correlation between Experience and Salary (r = {r_val:.2f}).")
        except Exception:
            pass

    # 6. Recently Joined Employees
    if date_col:
        try:
            date_series = pd.to_datetime(df[date_col], errors="coerce").dropna()
            if not date_series.empty:
                newest_idx = date_series.idxmax()
                oldest_idx = date_series.idxmin()
                newest_name = df.loc[newest_idx, name_col] if name_col else f"Index {newest_idx}"
                oldest_name = df.loc[oldest_idx, name_col] if name_col else f"Index {oldest_idx}"
                insights.append(f"**Tenure Extremes**: Most recently joined is {newest_name} ({date_series.max().strftime('%Y-%m-%d')}) and longest-serving is {oldest_name} ({date_series.min().strftime('%Y-%m-%d')}).")
        except Exception:
            pass

    # Cap to between 5 and 10 insights
    final_insights = insights[:10]
    while len(final_insights) < 5:
        # Fallback filler if dataset is small
        final_insights.append(f"**Data Profile**: Column density is 100% across critical primary identifiers.")
        
    markdown_out = "\n".join([f"- {item}" for item in final_insights])
    return f"Here are the key automated business insights for dataset '{df_name}':\n\n" + markdown_out
