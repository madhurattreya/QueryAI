import os
import json
from datetime import datetime
from backend.services.loader import DATA_DIR

LOG_FILE = os.path.join(DATA_DIR, "studio_logs.jsonl")

def log_telemetry(metrics: dict):
    """
    Appends a structured JSON log entry to the studio telemetry logs.
    """
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    # Merge with timestamp
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        **metrics
    }
    
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass

def get_telemetry_stats() -> dict:
    """
    Reads the telemetry logs and returns aggregated statistics for the observability dashboard.
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
                data = json.loads(line)
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
                if data.get("status") == "error" or data.get("error") is not None:
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
