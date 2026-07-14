import uuid
import time
import threading
from datetime import datetime
import backend.services.history_db as db

class SchedulerService:
    _instance = None
    _thread = None
    _running = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SchedulerService, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def start_scheduler(self):
        """
        Starts the background scheduled reports execution loop.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[SCHEDULER] Background reports scheduler thread started.")

    def stop_scheduler(self):
        self._running = False

    def register_job(self, dashboard_id: str, cron_expr: str, format_str: str, email: str) -> str:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        job_id = str(uuid.uuid4())
        
        cursor.execute(
            """
            INSERT INTO scheduler_jobs (id, dashboard_id, cron_expression, export_format, email_recipient, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            """,
            (job_id, dashboard_id, cron_expr, format_str, email)
        )
        conn.commit()
        conn.close()
        return job_id

    def list_jobs(self) -> list:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scheduler_jobs")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def delete_job(self, job_id: str):
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM scheduler_jobs WHERE id = ?", (job_id,))
        conn.commit()
        conn.close()

    def _run_loop(self):
        """
        Simulated scheduler execution loop. Scans active jobs and simulates report generation.
        """
        while self._running:
            try:
                conn = db.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM scheduler_jobs WHERE status = 'active'")
                jobs = [dict(row) for row in cursor.fetchall()]
                
                now = datetime.now()
                for job in jobs:
                    # Simulation: runs every 60 seconds if last_run_time is null or older than 60s
                    last_run = job["last_run_time"]
                    should_run = False
                    if not last_run:
                        should_run = True
                    else:
                        try:
                            last_run_dt = datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S.%f")
                        except Exception:
                            try:
                                last_run_dt = datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S")
                            except Exception:
                                last_run_dt = None
                                
                        if last_run_dt and (now - last_run_dt).total_seconds() > 60:
                            should_run = True
                            
                    if should_run:
                        print(f"[SCHEDULER RUN] Exporting dashboard {job['dashboard_id']} as {job['export_format']} to {job['email_recipient']}")
                        cursor.execute(
                            "UPDATE scheduler_jobs SET last_run_time = ? WHERE id = ?",
                            (now, job["id"])
                        )
                        conn.commit()
                conn.close()
            except Exception as e:
                print(f"[SCHEDULER ERROR] {str(e)}")
            time.sleep(30) # check every 30 seconds
