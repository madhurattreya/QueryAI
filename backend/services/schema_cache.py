import os
import pandas as pd
from sqlalchemy import inspect
import backend.config as config
from backend.services.profiler import profile_dataset, format_profile_for_prompt

# Globals memory cache
_schemas_cache = {}  # Key: name/table, Value: schema string
_profiles_cache = {}  # Key: name/table, Value: profile string

def clear_schema_cache():
    """
    Clears the cached schemas and profiles when a database reconnects or a new dataset is uploaded.
    """
    global _schemas_cache, _profiles_cache
    _schemas_cache.clear()
    _profiles_cache.clear()

def get_table_schema(name: str) -> str:
    """
    Retrieves and caches the database table or dataframe schema description.
    """
    global _schemas_cache
    
    if config.current_source_type == "sql" and config.database_engine:
        db_url = str(config.database_engine.url)
        cache_key = f"sql:{db_url}:{name}"
        if cache_key in _schemas_cache:
            return _schemas_cache[cache_key]
            
        try:
            inspector = inspect(config.database_engine)
            columns = inspector.get_columns(name)
            # Strip BOM characters from column names (common when CSVs are imported into MySQL)
            col_desc = ", ".join([f"{col['name'].lstrip('\ufeff')} ({col['type']})" for col in columns])
            schema_desc = f"Table: {name}\nColumns: {col_desc}\n"
            _schemas_cache[cache_key] = schema_desc
            return schema_desc
        except Exception as e:
            return f"Table: {name} (Error reading schema: {str(e)})\n"
    else:
        # File DataFrames
        if name not in config.datasets:
            return ""
        df = config.datasets[name]
        cache_key = f"file:{name}:{df.shape[0]}x{df.shape[1]}"
        if cache_key in _schemas_cache:
            return _schemas_cache[cache_key]
            
        # Standard schema format (max 5 sample rows)
        sample_rows = df.head(5).to_string(index=False)
        schema_desc = f"Dataset: {name}\nColumns and Types:\n{df.dtypes.to_string()}\nFirst 5 sample rows:\n{sample_rows}\n"
        _schemas_cache[cache_key] = schema_desc
        return schema_desc

def get_table_profile(name: str) -> str:
    """
    Retrieves and caches the statistical profile description of the dataset/table.
    """
    global _profiles_cache
    
    if config.current_source_type == "sql" and config.database_engine:
        # For SQL, we don't calculate heavy statistical correlations on the fly.
        # We can run simple queries for profiling, or keep it basic.
        # Let's keep it basic for performance, or fetch row count & min/max if needed.
        db_url = str(config.database_engine.url)
        cache_key = f"sql:{db_url}:{name}"
        if cache_key in _profiles_cache:
            return _profiles_cache[cache_key]
            
        try:
            inspector = inspect(config.database_engine)
            columns = inspector.get_columns(name)
            # Strip BOM characters from column names
            desc = f"Table: {name}\nColumns: " + ", ".join([col['name'].lstrip('\ufeff') for col in columns]) + "\n"
            _profiles_cache[cache_key] = desc
            return desc
        except Exception:
            return ""
    else:
        # File DataFrames
        if name not in config.datasets:
            return ""
        df = config.datasets[name]
        cache_key = f"file:{name}:{df.shape[0]}x{df.shape[1]}"
        if cache_key in _profiles_cache:
            return _profiles_cache[cache_key]
            
        profile_json = profile_dataset(name, df)
        profile_desc = format_profile_for_prompt(profile_json)
        _profiles_cache[cache_key] = profile_desc
        return profile_desc
