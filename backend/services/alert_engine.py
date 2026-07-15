import uuid
import time
import threading
from datetime import datetime
import backend.config as config
import backend.services.history_db as db

class AlertEngineService:
    _instance = None
    _thread = None
    _running = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(AlertEngineService, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def start_alerts_engine(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[ALERT ENGINE] Background alerts evaluator thread started.")

    def stop_alerts_engine(self):
        self._running = False

    def create_alert(self, dataset_id: str, col: str, cond: str, threshold: float, email: str) -> str:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        alert_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO alerts (id, dataset_id, metric_column, condition, threshold_value, email_recipient, triggered)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (alert_id, dataset_id, col, cond, threshold, email)
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

    def register_alert(self, dataset_id: str, col: str, cond: str, threshold: float, email: str) -> str:
        return self.create_alert(dataset_id, col, cond, threshold, email)

    def delete_alert(self, alert_id: str):
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()

    def start_monitoring(self):
        self.start_alerts_engine()

    def _run_loop(self):
        while self._running:
            try:
                conn = db.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM alerts")
                alerts = [dict(row) for row in cursor.fetchall()]
                
                # Check active datasets loaded in memory
                active_dataset_name = None
                for name in config.datasets.keys():
                    active_dataset_name = name
                    break
                    
                if active_dataset_name and config.datasets.get(active_dataset_name) is not None:
                    df = config.datasets[active_dataset_name]
                    
                    for alert in alerts:
                        col = alert["metric_column"]
                        if col in df.columns:
                            # Evaluate metric (sum of the column for simplicity)
                            val = float(df[col].sum())
                            cond = alert["condition"]
                            thresh = float(alert["threshold_value"])
                            
                            triggered = False
                            if cond == "<" and val < thresh:
                                triggered = True
                            elif cond == ">" and val > thresh:
                                triggered = True
                            elif cond == "=" and val == thresh:
                                triggered = True
                                
                            if triggered and alert["triggered"] == 0:
                                # Trigger alert notification
                                msg = f"ALERT TRIGGERED: Metric {col} has violated threshold. Current aggregate: {val:.2f} (Condition: {cond} {thresh})"
                                print(f"[ALERT TRIGGER] {msg}")
                                
                                # Save to Notifications table
                                notif_id = str(uuid.uuid4())
                                cursor.execute(
                                    "INSERT INTO notifications (id, username, message, is_read) VALUES (?, 'admin', ?, 0)",
                                    (notif_id, msg)
                                )
                                # Update alert triggered state
                                cursor.execute("UPDATE alerts SET triggered = 1, last_checked_time = ? WHERE id = ?", (datetime.now(), alert["id"]))
                                conn.commit()
                            elif not triggered and alert["triggered"] == 1:
                                # Reset trigger if condition resolved
                                cursor.execute("UPDATE alerts SET triggered = 0, last_checked_time = ? WHERE id = ?", (datetime.now(), alert["id"]))
                                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[ALERT ENGINE ERROR] {str(e)}")
            time.sleep(30) # check every 30 seconds

AlertEngine = AlertEngineService
