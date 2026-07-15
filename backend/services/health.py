import time
import pandas as pd
import numpy as np
import backend.config as config
from backend.services.insight_engine import run_result_heuristics

class DatasetHealthService:
    def calculate_health(self, dataset_name: str) -> dict:
        df = config.datasets.get(dataset_name)
        if df is None:
            raise ValueError(f"Dataset '{dataset_name}' not loaded.")

        total_rows = len(df)
        total_cols = len(df.columns)
        
        # 1. Missing Percentage
        missing_count = df.isnull().sum().to_dict()
        missing_pct = {k: round(v / total_rows * 100, 2) for k, v in missing_count.items()}
        total_missing_cells = df.isnull().sum().sum()
        total_cells = total_rows * total_cols
        overall_missing_pct = round(total_missing_cells / total_cells * 100, 2) if total_cells > 0 else 0.0

        # 2. Duplicates
        duplicates_count = int(df.duplicated().sum())
        duplicates_pct = round(duplicates_count / total_rows * 100, 2) if total_rows > 0 else 0.0

        # 3. Null Columns
        null_cols = [k for k, v in missing_pct.items() if v == 100.0]

        # 4. Outliers (using IQR method)
        numeric_cols = df.select_dtypes(include=[np.number])
        outliers = {}
        for col in numeric_cols.columns:
            q1 = numeric_cols[col].quantile(0.25)
            q3 = numeric_cols[col].quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outlier_mask = (numeric_cols[col] < lower) | (numeric_cols[col] > upper)
            cnt = int(outlier_mask.sum())
            if cnt > 0:
                outliers[col] = {
                    "count": cnt,
                    "percentage": round(cnt / total_rows * 100, 2)
                }

        # 5. Skewness
        skewness = {}
        for col in numeric_cols.columns:
            val = numeric_cols[col].skew()
            if not pd.isnull(val):
                skewness[col] = round(float(val), 3)

        # 6. Correlation Matrix
        high_correlations = []
        if len(numeric_cols.columns) >= 2:
            try:
                corr_matrix = numeric_cols.corr()
                cols_list = corr_matrix.columns.tolist()
                for i in range(len(cols_list)):
                    for j in range(i+1, len(cols_list)):
                        val = corr_matrix.iloc[i, j]
                        if not pd.isnull(val) and abs(val) > 0.6:
                            high_correlations.append({
                                "col1": cols_list[i],
                                "col2": cols_list[j],
                                "r": round(float(val), 2)
                            })
            except Exception:
                pass

        # 7. Data Freshness
        freshness = "Unknown"
        date_cols = df.select_dtypes(include=['datetime', 'datetimetz'])
        if not date_cols.empty:
            max_date = date_cols.iloc[:, 0].max()
            if pd.notnull(max_date):
                freshness = str(max_date)
        else:
            # Try parsing columns with date-like names
            for col in df.columns:
                if any(x in col.lower() for x in ["date", "time", "timestamp"]):
                    try:
                        parsed = pd.to_datetime(df[col], errors='coerce')
                        max_date = parsed.max()
                        if pd.notnull(max_date):
                            freshness = str(max_date)
                            break
                    except Exception:
                        pass

        # 8. Recommended Fixes
        recommended_fixes = []
        if duplicates_count > 0:
            recommended_fixes.append({
                "issue": f"Dataset contains {duplicates_count} exact duplicate rows.",
                "fix": "Remove duplicates to prevent double-counting metrics."
            })
        for col, pct in missing_pct.items():
            if pct > 40.0:
                recommended_fixes.append({
                    "issue": f"Column '{col}' has {pct}% missing values.",
                    "fix": "Impute values with median/mode or drop column if not useful."
                })
        for col, details in outliers.items():
            if details["percentage"] > 5.0:
                recommended_fixes.append({
                    "issue": f"Column '{col}' has {details['count']} outliers ({details['percentage']}%).",
                    "fix": "Apply log transformation or cap outliers to stabilize predictions."
                })
        if null_cols:
            recommended_fixes.append({
                "issue": f"Columns {null_cols} are entirely empty (100% missing values).",
                "fix": "Drop these empty columns to clean dataset schema."
            })

        if not recommended_fixes:
            recommended_fixes.append({
                "issue": "No critical quality issues detected.",
                "fix": "Data is clean and ready for analysis."
            })

        return {
            "dataset_name": dataset_name,
            "total_rows": total_rows,
            "total_columns": total_cols,
            "overall_missing_pct": overall_missing_pct,
            "missing_pct_per_column": missing_pct,
            "duplicates_count": duplicates_count,
            "duplicates_pct": duplicates_pct,
            "null_columns": null_cols,
            "outliers": outliers,
            "skewness": skewness,
            "high_correlations": high_correlations,
            "freshness": freshness,
            "recommended_fixes": recommended_fixes
        }
