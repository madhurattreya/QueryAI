"""
backend/services/logger.py
──────────────────────────
Structured telemetry and application logging with:
  - Severity log levels (INFO, WARNING, ERROR)
  - Correlation tracking via Request IDs
  - Structured LLM metrics logging
"""
import os
import json
from datetime import datetime
from typing import Any, Dict, Optional
from backend.services.loader import DATA_DIR

LOG_FILE = os.path.join(DATA_DIR, "studio_logs.jsonl")


def log_telemetry(metrics: dict, level: str = "INFO", request_id: Optional[str] = None):
    """
    Appends a structured JSON log entry to the studio telemetry logs.
    Includes severity level and correlation request ID.
    """
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    # Merge with meta
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level.upper(),
        "request_id": request_id or "system",
        **metrics
    }
    
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"[LOGGER ERROR] Failed to write telemetry log: {e}")


def log_info(message: str, request_id: Optional[str] = None, **kwargs):
    log_telemetry({"message": message, **kwargs}, level="INFO", request_id=request_id)


def log_warn(message: str, request_id: Optional[str] = None, **kwargs):
    log_telemetry({"message": message, **kwargs}, level="WARNING", request_id=request_id)


def log_error(message: str, request_id: Optional[str] = None, **kwargs):
    log_telemetry({"message": message, **kwargs}, level="ERROR", request_id=request_id)


def get_telemetry_stats() -> dict:
    """
    Reads telemetry logs and returns aggregated statistics for the observability dashboard.
    Gracefully handles missing keys and new structured schemas.
    """
    if not os.path.exists(LOG_FILE):
        return {
            "avg_response_time": 0.0,
            "avg_llm_latency": 0.0,
            "avg_execution_latency": 0.0,
            "cache_hit_rate": 0.0,
            "total_queries": 0,
            "failed_queries": 0,
            "auto_retry_count": 0,
            "avg_prompt_tokens": 0,
            "engine_counts": {}
        }
        
    total_time = 0.0
    total_llm_time = 0.0
    total_exec_time = 0.0
    cache_hits = 0
    total_queries = 0
    failed_queries = 0
    auto_retries = 0
    total_prompt_tokens = 0
    engine_counts = {}
    
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    # Skip internal message-only logs that are not query events
                    if "message" in data and "engine_used" not in data:
                        continue

                    total_queries += 1
                    total_time += data.get("execution_time", 0.0)
                    
                    # LLM Latency
                    llm_lat = data.get("timings", {}).get("llm_total_latency", 0.0)
                    total_llm_time += llm_lat
                    
                    # Exec Latency
                    exec_lat = data.get("timings", {}).get("sql_pandas_execution", 0.0)
                    total_exec_time += exec_lat
                    
                    # Cache
                    if data.get("cache_hit", False):
                        cache_hits += 1
                        
                    # Failures
                    if data.get("status") == "error" or data.get("level") == "ERROR" or data.get("error") is not None:
                        failed_queries += 1
                        
                    # Auto retry
                    if data.get("auto_retry_count", 0) > 0:
                        auto_retries += data.get("auto_retry_count")
                        
                    # Tokens
                    total_prompt_tokens += data.get("prompt_size", 0)
                    
                    # Engine
                    eng = data.get("engine_used", "unknown")
                    engine_counts[eng] = engine_counts.get(eng, 0) + 1
                except Exception:
                    pass
    except Exception:
        pass
        
    avg_response = total_time / total_queries if total_queries > 0 else 0.0
    avg_llm = total_llm_time / total_queries if total_queries > 0 else 0.0
    avg_exec = total_exec_time / total_queries if total_queries > 0 else 0.0
    cache_rate = (cache_hits / total_queries) * 100 if total_queries > 0 else 0.0
    avg_tokens = total_prompt_tokens / total_queries if total_queries > 0 else 0
    
    return {
        "avg_response_time": round(avg_response, 3),
        "avg_llm_latency": round(avg_llm, 3),
        "avg_execution_latency": round(avg_exec, 3),
        "cache_hit_rate": round(cache_rate, 2),
        "total_queries": total_queries,
        "failed_queries": failed_queries,
        "auto_retry_count": auto_retries,
        "avg_prompt_tokens": int(avg_tokens),
        "engine_counts": engine_counts
    }
