import uuid
import time
import threading
from datetime import datetime
import pandas as pd
import backend.config as config
import backend.services.history_db as db

class AlertEngine:
    _instance = None
    _thread = None
    _running = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(AlertEngine, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def start_monitoring(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[ALERT ENGINE] Background data monitoring thread started.")

    def stop_monitoring(self):
        self._running = False

    def register_alert(self, dataset_id: str, col: str, cond: str, val: float, email: str) -> str:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        alert_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO alerts (id, dataset_id, metric_column, condition, threshold_value, email_recipient)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (alert_id, dataset_id, col, cond, val, email)
        )
        conn.commit()
        conn.close()
        return alert_id

    def list_alerts(self, dataset_id: str = None) -> list:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        if dataset_id:
            cursor.execute("SELECT * FROM alerts WHERE dataset_id = ?", (dataset_id,))
        else:
            cursor.execute("SELECT * FROM alerts")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def delete_alert(self, alert_id: str):
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()

    def _run_loop(self):
        while self._running:
            try:
                conn = db.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM alerts")
                alerts = [dict(row) for row in cursor.fetchall()]
                
                # Fetch dataset mappings
                cursor.execute("SELECT id, name, filename FROM datasets")
                ds_map = {row["id"]: (row["name"], row["filename"]) for row in cursor.fetchall()}
                
                now = datetime.now()
                from backend.services.loader import DATA_DIR
                import os
                
                for alert in alerts:
                    ds_info = ds_map.get(alert["dataset_id"])
                    if not ds_info:
                        continue
                    
                    ds_name, filename = ds_info
                    # Load data (use config.datasets if loaded, or read file)
                    df = None
                    if ds_name in config.datasets:
                        df = config.datasets[ds_name]
                    else:
                        filepath = os.path.join(DATA_DIR, filename)
                        if os.path.exists(filepath):
                            try:
                                ext = os.path.splitext(filename)[1].lower()
                                df = pd.read_csv(filepath) if ext == ".csv" else pd.read_excel(filepath)
                            except Exception:
                                pass
                                
                    if df is None or df.empty or alert["metric_column"] not in df.columns:
                        continue
                        
                    # Calculate aggregated value (e.g. sum of column) to test threshold
                    metric_val = float(df[alert["metric_column"]].sum())
                    cond = alert["condition"]
                    thresh = float(alert["threshold_value"])
                    
                    is_triggered = False
                    if cond == ">" and metric_val > thresh:
                        is_triggered = True
                    elif cond == "<" and metric_val < thresh:
                        is_triggered = True
                    elif cond == "==" and metric_val == thresh:
                        is_triggered = True
                        
                    if is_triggered:
                        print(f"[ALERT TRIGGERED] Metric {alert['metric_column']} sum ({metric_val}) is {cond} threshold ({thresh}) on dataset {ds_name}! Sent alert to {alert['email_recipient']}.")
                        cursor.execute(
                            "UPDATE alerts SET last_checked_time = ?, triggered = 1 WHERE id = ?",
                            (now, alert["id"])
                        )
                    else:
                        cursor.execute(
                            "UPDATE alerts SET last_checked_time = ?, triggered = 0 WHERE id = ?",
                            (now, alert["id"])
                        )
                    conn.commit()
                conn.close()
            except Exception as e:
                print(f"[ALERT ENGINE ERROR] {str(e)}")
            time.sleep(30) # run monitoring every 30 seconds
