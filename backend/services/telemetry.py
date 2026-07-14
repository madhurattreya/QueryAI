import os
import uuid
import psutil
import backend.services.history_db as db

class TelemetryService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TelemetryService, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def log_metric(self, name: str, value: float):
        """
        Saves a metric log to SQLite telemetry table.
        """
        try:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO telemetry_logs (id, metric_name, metric_value)
                VALUES (?, ?, ?)
                """,
                (str(uuid.uuid4()), name, value)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[TELEMETRY LOG WARNING] Failed to save metric {name}: {e}")

    def collect_system_metrics(self) -> dict:
        """
        Gathers live host CPU, Memory, and processes metrics.
        """
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            process = psutil.Process(os.getpid())
            process_mem = process.memory_info().rss / (1024 * 1024) # MB
            
            # Log metrics to db
            self.log_metric("host_cpu_percent", cpu)
            self.log_metric("host_mem_percent", mem.percent)
            self.log_metric("process_memory_mb", process_mem)
            
            return {
                "cpu_percent": cpu,
                "memory_percent": mem.percent,
                "process_memory_mb": round(process_mem, 2),
                "available_memory_gb": round(mem.available / (1024**3), 2)
            }
        except Exception as e:
            return {
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "process_memory_mb": 0.0,
                "error": str(e)
            }

    def get_aggregated_telemetry(self) -> dict:
        """
        Fetches historic averages for latency and success metrics.
        """
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Avg Latency
        cursor.execute("SELECT AVG(execution_time) as avg_lat FROM messages WHERE execution_time IS NOT NULL")
        avg_lat = cursor.fetchone()["avg_lat"] or 0.0
        
        # 2. Engine Share
        cursor.execute("SELECT engine_used, COUNT(*) as cnt FROM messages GROUP BY engine_used")
        shares = {row["engine_used"] or "unknown": row["cnt"] for row in cursor.fetchall()}
        
        # 3. Total Queries
        cursor.execute("SELECT COUNT(*) as tot FROM messages")
        total_queries = cursor.fetchone()["tot"] or 0
        
        conn.close()
        
        sys_metrics = self.collect_system_metrics()
        return {
            "avg_latency_s": round(avg_lat, 4),
            "engine_shares": shares,
            "total_queries": total_queries,
            "system": sys_metrics
        }
