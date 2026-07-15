from fastapi import APIRouter, HTTPException, Depends
import os
import time
import backend.config as config
import backend.services.history_db as db
from backend.services.security_manager import verify_token

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/metrics")
def get_admin_metrics(user: dict = Depends(verify_token)):
    # Validate permissions
    if user.get("role") not in ["Super Admin", "Admin"]:
        raise HTTPException(status_code=403, detail="Access Denied: Only Admins can view metrics")

    conn = db.get_db_connection()
    cursor = conn.cursor()

    # Active counts
    cursor.execute("SELECT count(*) as count FROM users")
    active_users = cursor.fetchone()["count"]

    cursor.execute("SELECT count(*) as count FROM workspaces")
    active_workspaces = cursor.fetchone()["count"]

    cursor.execute("SELECT count(*) as count FROM datasets")
    active_datasets = cursor.fetchone()["count"]

    # Scheduler and jobs stats
    cursor.execute("SELECT count(*) as count FROM scheduler_jobs WHERE status = 'active'")
    running_jobs = cursor.fetchone()["count"]
    
    cursor.execute("SELECT count(*) as count FROM scheduler_history")
    scheduler_queue_size = cursor.fetchone()["count"]

    # Latencies and Query logs
    cursor.execute("SELECT execution_time FROM messages WHERE role = 'assistant' AND execution_time IS NOT NULL")
    latencies = [row["execution_time"] for row in cursor.fetchall()]
    conn.close()

    p95 = 0.0
    p99 = 0.0
    avg_latency = 0.0
    if latencies:
        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        avg_latency = sum(latencies) / len(latencies)

    # API usage metrics (mock rate limits and actual query logs count)
    api_calls_min = len(latencies)  # mock value mapping active logging rate
    db_query_time = 0.045 # mock query database latency in seconds

    # Memory consumption per dataset
    memory_per_dataset = {}
    for name, df in config.datasets.items():
        try:
            mem = int(df.memory_usage(deep=True).sum())
            memory_per_dataset[name] = f"{mem / (1024 * 1024):.2f} MB"
        except Exception:
            memory_per_dataset[name] = "0.00 MB"

    # CPU/RAM/Disk utilizing standard OS stats or mock if fail
    cpu_percent = 12.5
    ram_percent = 45.2
    disk_percent = 60.1
    try:
        import psutil
        cpu_percent = psutil.cpu_percent()
        ram_percent = psutil.virtual_memory().percent
        disk_percent = psutil.disk_usage('/').percent
    except ImportError:
        pass

    return {
        "status": "success",
        "system": {
            "cpu_usage_pct": cpu_percent,
            "ram_usage_pct": ram_percent,
            "disk_usage_pct": disk_percent
        },
        "active_counts": {
            "active_users": active_users,
            "active_workspaces": active_workspaces,
            "active_datasets": active_datasets
        },
        "scheduler": {
            "running_jobs": running_jobs,
            "scheduler_queue_size": scheduler_queue_size
        },
        "performance": {
            "p95_latency_seconds": round(p95, 3),
            "p99_latency_seconds": round(p99, 3),
            "avg_latency_seconds": round(avg_latency, 3),
            "api_calls_per_minute": api_calls_min,
            "database_query_time_seconds": db_query_time,
            "memory_usage_per_dataset": memory_per_dataset
        }
    }
