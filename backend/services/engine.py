import os
import re
import json
import csv
import hashlib
import difflib
import concurrent.futures
from datetime import datetime
import pandas as pd
import backend.config as config
from backend.services.loader import DATA_DIR

CACHE_FILE = os.path.join(DATA_DIR, "query_cache_v2.json")
HISTORY_FILE = os.path.join(DATA_DIR, "query_history.csv")

# Plotly Detector
try:
    import plotly.graph_objects as go
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False
    go = None
    px = None

def get_df_hash(df) -> str:
    """
    Computes a stable hash representation of a dataframe based on its shape and columns.
    """
    col_str = ",".join(df.columns)
    return f"{col_str}:{df.shape[0]}x{df.shape[1]}"

def get_sha256_cache_key(dataset_hash: str, question: str, conversation_id: str = "", selected_model: str = "", temperature: float = 0.0, dataset_version: str = "", router_type: str = "", prompt_template_hash: str = "", conversation_context_hash: str = "") -> str:
    """
    Generates a unique SHA-256 hash to use as cache key, incorporating model and dataset properties.
    """
    if not prompt_template_hash:
        from backend.services.prompt_builder import get_template
        template_text = get_template(router_type or "pandas")
        prompt_template_hash = hashlib.sha256(template_text.encode("utf-8")).hexdigest()
        
    if not conversation_context_hash and conversation_id:
        import backend.services.history_db as db
        conv = db.get_conversation(conversation_id)
        summary = conv.get("summary") if conv else ""
        conversation_context_hash = hashlib.sha256((summary or "").encode("utf-8")).hexdigest()
        
    raw_str = f"{dataset_hash}|{dataset_version}|{question.strip().lower()}|{router_type}|{prompt_template_hash}|{conversation_context_hash}"
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

_in_memory_cache = None

def load_cache() -> dict:
    global _in_memory_cache
    if _in_memory_cache is not None:
        return _in_memory_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _in_memory_cache = json.load(f)
                return _in_memory_cache
        except Exception:
            _in_memory_cache = {}
            return _in_memory_cache
    _in_memory_cache = {}
    return _in_memory_cache

def save_cache(cache: dict):
    global _in_memory_cache
    _in_memory_cache = cache

def persist_cache_to_disk():
    global _in_memory_cache
    if _in_memory_cache is None:
        return
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_in_memory_cache, f, indent=4)
    except Exception:
        pass

def get_cached_result(cache_key: str) -> dict | None:
    cache = load_cache()
    return cache.get(cache_key)

def set_cached_result(cache_key: str, val: dict):
    cache = load_cache()
    cache[cache_key] = val
    save_cache(cache)

def log_query(question: str, query: str, elapsed_time: float, rows_count: int):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    file_exists = os.path.exists(HISTORY_FILE)
    try:
        with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Question", "Generated Query", "Time Taken (sec)", "Rows Returned"])
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                question,
                query.replace("\n", "  ") if query else "FAILED",
                f"{elapsed_time:.2f}",
                rows_count
            ])
    except Exception:
        pass

def run_query_with_timeout(code, globals_dict, locals_dict, timeout=5):
    """
    Executes Python code in a sandboxed execution context with a CPU timeout limit.
    """
    # Enforce maximum DataFrame rows restriction in local dataframe assignments
    for key, val in list(locals_dict.items()):
        if isinstance(val, pd.DataFrame):
            if len(val) > 100000: # CAP rows loaded into memory
                locals_dict[key] = val.head(100000)
                
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(exec, code, globals_dict, locals_dict)
        try:
            future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Query execution timed out after {timeout} seconds.")

COMMON_TYPO_MAP = {
    "joiningdate": "JoinDate",
    "joining": "JoinDate",
    "joining_date": "JoinDate",
    "join_date": "JoinDate",
    "hire_date": "HireDate",
    "hiringdate": "HireDate",
    "departmant": "Department",
    "salry": "Salary",
    "salary_usd": "Salary",
    "experiance": "Experience",
    "employeid": "EmployeeID",
    "join year": "JoinDate",
    "joinyear": "JoinDate",
    "joiningyear": "JoinDate"
}

def fuzzy_find_columns(target: str, available_cols: list) -> str | None:
    """
    Finds a matching column from available columns using fuzzy string matching.
    """
    # Try case-insensitive exact match first
    for col in available_cols:
        if col.lower() == target.lower():
            return col
            
    matches = difflib.get_close_matches(target, available_cols, n=1, cutoff=0.6)
    return matches[0] if matches else None

def attempt_fast_correction(code: str, error: Exception, available_cols: list) -> str | None:
    """
    Attempts to perform rapid textual regex replacements in case of column reference issues.
    """
    error_msg = str(error)
    missing_col = None
    
    # 1. Parse missing column from exception
    if isinstance(error, KeyError):
        missing_col = str(error.args[0])
    else:
        # Check KeyError pattern in message
        key_err_match = re.search(r"KeyError:\s*['\"]([^'\"]+)['\"]", error_msg, re.IGNORECASE)
        attr_match = re.search(r"object has no attribute ['\"]([^'\"]+)['\"]", error_msg, re.IGNORECASE)
        col_match = re.search(r"no such column: (?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)", error_msg, re.IGNORECASE)
        
        if key_err_match:
            missing_col = key_err_match.group(1)
        elif attr_match:
            missing_col = attr_match.group(1)
        elif col_match:
            missing_col = col_match.group(1)
            
    if not missing_col:
        return None
        
    # Remove surrounding quotes if any
    missing_col = missing_col.strip("'\"")
    
    # 2. Check hardcoded typos
    closest = None
    clean_missing = missing_col.lower()
    if clean_missing in COMMON_TYPO_MAP:
        mapped_target = COMMON_TYPO_MAP[clean_missing]
        for col in available_cols:
            if col.lower() == mapped_target.lower():
                closest = col
                break
                
    # 3. Fallback to fuzzy match
    if not closest:
        closest = fuzzy_find_columns(missing_col, available_cols)
        
    if closest:
        print(f"[SELF-HEALING FAST PATH] Correcting '{missing_col}' -> '{closest}' in code.")
        # Replace occurrences of missing_col (either as a string key or identifier)
        corrected_code = re.sub(rf"\b{re.escape(missing_col)}\b", closest, code)
        return corrected_code
        
    return None
