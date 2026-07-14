import abc
import pandas as pd
from sqlalchemy import inspect, text
import backend.config as config

class BaseConnector(abc.ABC):
    """
    Abstract Base Class for all data source connectors.
    """
    @abc.abstractmethod
    def fetch_schema(self, table_name: str) -> str:
        pass

    @abc.abstractmethod
    def execute_query(self, query: str) -> pd.DataFrame:
        pass

    @abc.abstractmethod
    def profile_dataset(self, table_name: str) -> dict:
        pass

    @abc.abstractmethod
    def fetch_preview(self, table_name: str, limit: int = 5) -> pd.DataFrame:
        pass


class FileConnector(BaseConnector):
    """
    Connector for CSV and Excel files loaded in-memory as Pandas DataFrames.
    """
    def __init__(self, datasets_dict: dict):
        self.datasets = datasets_dict

    def fetch_schema(self, table_name: str) -> str:
        if table_name not in self.datasets:
            return ""
        df = self.datasets[table_name]
        col_desc = ", ".join([f"{col} ({dtype})" for col, dtype in zip(df.columns, df.dtypes)])
        return f"Dataset: {table_name}\nColumns: {col_desc}\n"

    def execute_query(self, query: str) -> pd.DataFrame:
        # For FileConnector, query execution runs via local Pandas evaluation.
        # This will be orchestrated by the main query sandbox.
        raise NotImplementedError("FileConnector uses local Pandas engine execution.")

    def profile_dataset(self, table_name: str) -> dict:
        if table_name not in self.datasets:
            return {}
        df = self.datasets[table_name]
        profile = {
            "dataset_name": table_name,
            "rows": df.shape[0],
            "columns_count": df.shape[1],
            "columns": []
        }
        for col in df.columns:
            col_type = str(df[col].dtype)
            unique_count = int(df[col].nunique())
            null_count = int(df[col].isnull().sum())
            col_stats = {
                "name": col,
                "type": col_type,
                "null_percentage": round((null_count / len(df)) * 100, 2) if len(df) > 0 else 0,
                "unique_count": unique_count
            }
            if pd.api.types.is_numeric_dtype(df[col]) and not df[col].empty:
                col_stats["min"] = float(df[col].min()) if not pd.isnull(df[col].min()) else None
                col_stats["max"] = float(df[col].max()) if not pd.isnull(df[col].max()) else None
                col_stats["mean"] = float(df[col].mean()) if not pd.isnull(df[col].mean()) else None
            profile["columns"].append(col_stats)
        return profile

    def fetch_preview(self, table_name: str, limit: int = 5) -> pd.DataFrame:
        if table_name in self.datasets:
            return self.datasets[table_name].head(limit)
        return pd.DataFrame()


class SQLConnector(BaseConnector):
    """
    Connector for SQL-based databases using SQLAlchemy (SQLite, MySQL, Postgres, SQL Server).
    """
    def __init__(self, engine, flavor: str = "SQL"):
        self.engine = engine
        self.flavor = flavor

    def fetch_schema(self, table_name: str) -> str:
        try:
            inspector = inspect(self.engine)
            columns = inspector.get_columns(table_name)
            col_desc = ", ".join([f"{col['name'].lstrip('\ufeff')} ({col['type']})" for col in columns])
            return f"Table: {table_name}\nColumns: {col_desc}\n"
        except Exception as e:
            return f"Table: {table_name} (Error: {str(e)})"

    def execute_query(self, query: str) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(query), conn)

    def profile_dataset(self, table_name: str) -> dict:
        try:
            inspector = inspect(self.engine)
            columns = inspector.get_columns(table_name)
            
            # Simple metadata-based profile
            profile = {
                "dataset_name": table_name,
                "rows": 0,
                "columns_count": len(columns),
                "columns": []
            }
            
            # Fetch row count
            with self.engine.connect() as conn:
                res = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                profile["rows"] = res.scalar()
                
            for col in columns:
                col_name = col['name'].lstrip('\ufeff')
                profile["columns"].append({
                    "name": col_name,
                    "type": str(col['type']),
                    "null_percentage": 0.0, # default placeholder
                    "unique_count": 0
                })
            return profile
        except Exception:
            return {}

    def fetch_preview(self, table_name: str, limit: int = 5) -> pd.DataFrame:
        query = f"SELECT * FROM {table_name} LIMIT {limit}"
        return self.execute_query(query)


# Future connectors stubs
class SnowflakeConnector(SQLConnector):
    pass

class BigQueryConnector(BaseConnector):
    def fetch_schema(self, table_name: str) -> str: pass
    def execute_query(self, query: str) -> pd.DataFrame: pass
    def profile_dataset(self, table_name: str) -> dict: pass
    def fetch_preview(self, table_name: str, limit: int = 5) -> pd.DataFrame: pass

class ClickHouseConnector(SQLConnector):
    pass

class DuckDBConnector(BaseConnector):
    def __init__(self, datasets_dict: dict):
        import duckdb
        self.conn = duckdb.connect(database=':memory:')
        self.datasets = datasets_dict
        for name, df in datasets_dict.items():
            self.conn.register(name, df)

    def fetch_schema(self, table_name: str) -> str:
        if table_name not in self.datasets:
            return ""
        df = self.datasets[table_name]
        col_desc = ", ".join([f"{col} ({dtype})" for col, dtype in zip(df.columns, df.dtypes)])
        return f"Dataset: {table_name}\nColumns: {col_desc}\n"

    def execute_query(self, query: str) -> pd.DataFrame:
        return self.conn.execute(query).df()

    def profile_dataset(self, table_name: str) -> dict:
        if table_name not in self.datasets:
            return {}
        df = self.datasets[table_name]
        profile = {
            "dataset_name": table_name,
            "rows": df.shape[0],
            "columns_count": df.shape[1],
            "columns": []
        }
        for col in df.columns:
            col_type = str(df[col].dtype)
            unique_count = int(df[col].nunique())
            null_count = int(df[col].isnull().sum())
            col_stats = {
                "name": col,
                "type": col_type,
                "null_percentage": round((null_count / len(df)) * 100, 2) if len(df) > 0 else 0,
                "unique_count": unique_count
            }
            if pd.api.types.is_numeric_dtype(df[col]) and not df[col].empty:
                col_stats["min"] = float(df[col].min()) if not pd.isnull(df[col].min()) else None
                col_stats["max"] = float(df[col].max()) if not pd.isnull(df[col].max()) else None
                col_stats["mean"] = float(df[col].mean()) if not pd.isnull(df[col].mean()) else None
            profile["columns"].append(col_stats)
        return profile

    def fetch_preview(self, table_name: str, limit: int = 5) -> pd.DataFrame:
        if table_name in self.datasets:
            return self.datasets[table_name].head(limit)
        return pd.DataFrame()

class DatabricksConnector(BaseConnector):
    def fetch_schema(self, table_name: str) -> str: pass
    def execute_query(self, query: str) -> pd.DataFrame: pass
    def profile_dataset(self, table_name: str) -> dict: pass
    def fetch_preview(self, table_name: str, limit: int = 5) -> pd.DataFrame: pass
