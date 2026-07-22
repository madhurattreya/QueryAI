import os
import gc
import json
import hashlib
import threading
from datetime import datetime
import pandas as pd
from sqlalchemy import create_engine, inspect
from cryptography.fernet import Fernet
import backend.config as config
import backend.services.history_db as db
from backend.services.loader import DATA_DIR
from backend.services.schema_cache import clear_schema_cache
from backend.services.engine import get_df_hash

# Global thread-safe execution lock (reentrant to prevent recursive deadlocks)
dataset_lock = threading.RLock()

KEY_FILE = os.path.join(DATA_DIR, "fernet.key")
PREVIEWS_DIR = os.path.join(DATA_DIR, "previews")

def get_fernet() -> Fernet:
    """
    Retrieves or generates a persistent Fernet key for credential encryption.
    """
    key = os.environ.get("FERNET_KEY")
    if key:
        return Fernet(key.encode("utf-8"))
        
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, "rb") as f:
                return Fernet(f.read().strip())
        except Exception:
            pass
            
    os.makedirs(DATA_DIR, exist_ok=True)
    new_key = Fernet.generate_key()
    try:
        with open(KEY_FILE, "wb") as f:
            f.write(new_key)
    except Exception:
        pass
    return Fernet(new_key)

def detect_date_columns(df: pd.DataFrame) -> list:
    date_cols = []
    date_keywords = ["date", "joined", "hired", "order_date", "order date", "order_time", "order time", "created", "invoice"]
    for col in df.columns:
        col_lower = col.lower()
        if any(kw in col_lower for kw in date_keywords):
            try:
                # Test parse first 20 values
                test_conv = pd.to_datetime(df[col].head(20), errors="coerce")
                if not test_conv.isnull().all():
                    date_cols.append(col)
            except Exception:
                pass
    return date_cols


def load_csv_safely(filepath: str, nrows: int = None) -> pd.DataFrame:
    """
    Robust CSV loader with automatic encoding detection (utf-8-sig, utf-8, latin1, cp1252),
    BOM cleanup, and delimiter auto-detection for European Excel exports.
    """
    for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
        try:
            df = pd.read_csv(filepath, nrows=nrows, encoding=enc)
            if len(df.columns) == 1 and ";" in str(df.columns[0]):
                df = pd.read_csv(filepath, nrows=nrows, encoding=enc, sep=";")
            return df
        except Exception:
            continue
    return pd.read_csv(filepath, nrows=nrows, encoding="latin1", on_bad_lines="skip")

class DatasetManager:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DatasetManager, cls).__new__(cls, *args, **kwargs)
            cls._instance.fernet = get_fernet()
        return cls._instance

    def encrypt_credentials(self, connection_info: dict) -> str:
        """
        Encrypts connection credentials using Fernet.
        """
        raw_json = json.dumps(connection_info)
        return self.fernet.encrypt(raw_json.encode("utf-8")).decode("utf-8")

    def decrypt_credentials(self, encrypted_str: str) -> dict:
        """
        Decrypts connection credentials.
        """
        if not encrypted_str:
            return {}
        decrypted_bytes = self.fernet.decrypt(encrypted_str.encode("utf-8"))
        return json.loads(decrypted_bytes.decode("utf-8"))

    def get_file_version_name(self, original_name: str, ext: str) -> tuple:
        """
        Calculates incremented filename version slug (e.g. employees_v2.csv) if clashing.
        """
        base_name = original_name.rstrip("1234567890_v")
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Match names with patterns
        cursor.execute("SELECT name FROM datasets WHERE name LIKE ?", (f"{base_name}%",))
        existing_names = [r["name"] for r in cursor.fetchall()]
        conn.close()
        
        if not existing_names:
            return original_name, f"{original_name}{ext}"
            
        version = 1
        while True:
            candidate_name = f"{base_name}_v{version}"
            if candidate_name not in existing_names:
                return candidate_name, f"{candidate_name}{ext}"
            version += 1

    def calculate_file_hash(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    def register_dataset_file(self, original_filename: str, source_path: str, behavior: str = "keep", user_id: str = None) -> dict:
        """
        Registers an uploaded file, checks hashes for duplicates, creates versions, and extracts headers.
        """
        with dataset_lock:
            file_hash = self.calculate_file_hash(source_path)
            size_bytes = os.path.getsize(source_path)
            
            # Check for identical duplicate owned by this user
            conn = db.get_db_connection()
            cursor = conn.cursor()
            if user_id:
                cursor.execute("SELECT * FROM datasets WHERE hash = ? AND (user_id = ? OR user_id IS NULL)", (file_hash, user_id))
            else:
                cursor.execute("SELECT * FROM datasets WHERE hash = ?", (file_hash,))
            existing = cursor.fetchone()
            
            if existing:
                conn.close()
                # Simply update last used and activate
                ds_id = existing["id"]
                self.activate_dataset_by_id(ds_id)
                return {
                    "status": "success",
                    "duplicate": True,
                    "id": ds_id,
                    "dataset_id": ds_id,
                    "name": existing["name"]
                }
            
            conn.close()
                
            # If behavior == "replace", purge all previous datasets
            if behavior == "replace":
                self.clear_all_datasets_unsafe()
                
            # Resolve name version
            base_name, ext = os.path.splitext(original_filename)
            normalized_name = base_name.strip().lower().replace(" ", "_")
            ds_name, version_filename = self.get_file_version_name(normalized_name, ext.lower())
            
            # Save file to uploads folder
            target_path = os.path.join(DATA_DIR, version_filename)
            if os.path.abspath(source_path) != os.path.abspath(target_path):
                import shutil
                shutil.copy2(source_path, target_path)
            
            # Read only first 5 rows to extract schema without high memory footprint
            try:
                if ext.lower() == ".csv":
                    header_df = load_csv_safely(target_path, nrows=5)
                else:
                    header_df = pd.read_excel(target_path, nrows=5)
                cols_count = len(header_df.columns)
                # Quick row count estimate
                if ext.lower() == ".csv":
                    with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                        rows_count = sum(1 for _ in f) - 1
                else:
                    rows_count = len(pd.read_excel(target_path)) # Excel requires parsing
            except Exception:
                cols_count = 0
                rows_count = 0
                
            # Run date detection
            date_cols = []
            try:
                date_cols = detect_date_columns(header_df)
            except Exception:
                pass
            date_columns_json = json.dumps(date_cols)

            ds_id = str(hashlib.md5(f"{ds_name}_{user_id or ''}".encode()).hexdigest())
            
            # Insert dataset record with a fresh connection
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO datasets (id, name, filename, source, type, hash, rows, columns, size_bytes, is_active, status, upload_time, last_used_time, date_columns, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ds_id, ds_name, version_filename, ext[1:].upper(), "file", file_hash, rows_count, cols_count, size_bytes, 1, "active", datetime.now(), datetime.now(), date_columns_json, user_id))
            
            # Mark others inactive for this user
            if user_id:
                cursor.execute("UPDATE datasets SET is_active = 0, status = 'inactive' WHERE id != ? AND user_id = ?", (ds_id, user_id))
            else:
                cursor.execute("UPDATE datasets SET is_active = 0, status = 'inactive' WHERE id != ?", (ds_id,))
            conn.commit()
            conn.close()
            
            # Clear caches and load into RAM
            clear_schema_cache()
            if ext.lower() == ".csv":
                loaded_df = load_csv_safely(target_path)
            else:
                loaded_df = pd.read_excel(target_path)
                
            for col in date_cols:
                if col in loaded_df.columns:
                    loaded_df[col] = pd.to_datetime(loaded_df[col], errors="coerce")
            config.datasets = {ds_name: loaded_df}
            config.current_source_type = "file"
            config.database_engine = None
            
            # Queue background profiling task
            threading.Thread(target=self.run_background_profiler, args=(ds_name, ds_id)).start()
            
            return {
                "status": "success",
                "duplicate": False,
                "id": ds_id,
                "dataset_id": ds_id,
                "name": ds_name
            }

    def register_sql_connection(self, name: str, db_type: str, connection_params: dict) -> dict:
        """
        Encrypts connection credentials and registers a SQL server connection as a active dataset.
        """
        with dataset_lock:
            # Obfuscate / encrypt parameters
            encrypted_creds = self.encrypt_credentials(connection_params)
            
            conn = db.get_db_connection()
            cursor = conn.cursor()
            
            ds_name = name.strip().lower().replace(" ", "_")
            ds_id = str(hashlib.md5(ds_name.encode()).hexdigest())
            
            # Check duplicate database connection
            cursor.execute("SELECT * FROM datasets WHERE id = ?", (ds_id,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute("UPDATE datasets SET connection_info = ?, last_used_time = ?, is_active = 1 WHERE id = ?", (encrypted_creds, datetime.now(), ds_id))
            else:
                cursor.execute("""
                    INSERT INTO datasets (id, name, filename, source, type, hash, rows, columns, size_bytes, is_active, status, connection_info, upload_time, last_used_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ds_id, ds_name, None, db_type.upper(), "sql", "", 0, 0, 0, 1, "active", encrypted_creds, datetime.now(), datetime.now()))
                
            cursor.execute("UPDATE datasets SET is_active = 0, status = 'inactive' WHERE id != ?", (ds_id,))
            conn.commit()
            conn.close()
            
            # Unload any loaded files from RAM
            config.datasets.clear()
            clear_schema_cache()
            
            # Reconnect active engine
            from backend.services.loader import create_db_engine
            engine_obj, flavor = create_db_engine(
                db_type=db_type,
                sqlite_path=connection_params.get("sqlite_path"),
                host=connection_params.get("host", "localhost"),
                port=connection_params.get("port"),
                db_name=connection_params.get("db_name", ""),
                username=connection_params.get("username", ""),
                password=connection_params.get("password", "")
            )
            config.database_engine = engine_obj
            config.db_flavor = flavor
            config.current_source_type = "sql"
            
            return {
                "status": "success",
                "dataset_id": ds_id,
                "name": ds_name
            }

    def activate_dataset_by_id(self, dataset_id: str, user_id: str = None):
        """
        Thread-safe dataset switching with complete memory cleanup and cache resets.
        """
        self.activate_datasets_multiple([dataset_id], user_id=user_id)

    def activate_datasets_multiple(self, dataset_ids: list, user_id: str = None):
        """
        Thread-safe multi-dataset activation. Loads all specified datasets into config.datasets.
        """
        with dataset_lock:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            
            # Perform complete memory cleanup
            config.datasets.clear()
            config.database_engine = None
            clear_schema_cache()
            
            # Invalidate result cache
            from backend.services.engine import CACHE_FILE
            if os.path.exists(CACHE_FILE):
                try: os.remove(CACHE_FILE)
                except Exception: pass
                
            # Switch registry statuses scoped by user
            if user_id:
                cursor.execute("UPDATE datasets SET is_active = 0, status = 'inactive' WHERE user_id = ?", (user_id,))
            else:
                cursor.execute("UPDATE datasets SET is_active = 0, status = 'inactive'")
            
            loaded_dfs = {}
            for ds_id in dataset_ids:
                if user_id:
                    cursor.execute("SELECT * FROM datasets WHERE id = ? AND (user_id = ? OR user_id IS NULL)", (ds_id, user_id))
                else:
                    cursor.execute("SELECT * FROM datasets WHERE id = ?", (ds_id,))
                row = cursor.fetchone()
                if not row:
                    continue
                    
                cursor.execute("UPDATE datasets SET is_active = 1, status = 'active', last_used_time = ? WHERE id = ?", (datetime.now(), ds_id))
                
                if row["type"] == "file":
                    filepath = os.path.join(DATA_DIR, row["filename"])
                    ext = os.path.splitext(row["filename"])[1].lower()
                    
                    if ext == ".csv":
                        df = pd.read_csv(filepath)
                    else:
                        df = pd.read_excel(filepath)
                        
                    # Convert dates if specified in registry metadata
                    try:
                        date_cols_str = row["date_columns"]
                        if date_cols_str:
                            date_cols = json.loads(date_cols_str)
                            for col in date_cols:
                                if col in df.columns:
                                    df[col] = pd.to_datetime(df[col], errors="coerce")
                    except Exception:
                        pass
                        
                    loaded_dfs[row["name"]] = df
                    config.current_source_type = "file"
                else:
                    # Re-establish SQL Engine connection
                    creds = self.decrypt_credentials(row["connection_info"])
                    from backend.services.loader import create_db_engine
                    engine_obj, flavor = create_db_engine(
                        db_type=row["source"].lower(),
                        sqlite_path=creds.get("sqlite_path"),
                        host=creds.get("host", "localhost"),
                        port=creds.get("port"),
                        db_name=creds.get("db_name", ""),
                        username=creds.get("username", ""),
                        password=creds.get("password", "")
                    )
                    config.database_engine = engine_obj
                    config.db_flavor = flavor
                    config.current_source_type = "sql"
                    # Auto-fix BOM-prefixed column names in SQL databases
                    self._fix_bom_columns(engine_obj, flavor)
                    
            config.datasets = loaded_dfs
            
            # Build and register Schema Index for each activated dataset
            from backend.services.schema_index import SchemaIndexRegistry
            for name, df in loaded_dfs.items():
                try:
                    SchemaIndexRegistry.build_or_refresh(name, df)
                    print(f"[SCHEMA INDEX] Built and registered index for: {name}")
                except Exception as ex:
                    print(f"[SCHEMA INDEX WARNING] Failed to build index for {name}: {ex}")

            conn.commit()
            conn.close()
            
            # Force trigger garbage collection
            gc.collect()


    def _fix_bom_columns(self, engine_obj, flavor: str):
        """
        Scans all tables in a SQL database for BOM-prefixed column names and renames them.
        BOM characters (\ufeff) are commonly introduced when MySQL imports BOM-encoded CSV files.
        This is a non-destructive in-place fix that runs silently.
        """
        try:
            from sqlalchemy import inspect as sa_inspect, text
            inspector = sa_inspect(engine_obj)
            tables = inspector.get_table_names()
            with engine_obj.begin() as conn:
                for table in tables:
                    cols = inspector.get_columns(table)
                    for col in cols:
                        col_name = col['name']
                        if col_name.startswith('\ufeff'):
                            clean_name = col_name.lstrip('\ufeff')
                            col_type = str(col['type'])
                            try:
                                if flavor in ("mysql", "mariadb"):
                                    # MySQL uses: ALTER TABLE t CHANGE `old` `new` TYPE
                                    conn.execute(text(
                                        f"ALTER TABLE `{table}` CHANGE `{col_name}` `{clean_name}` {col_type}"
                                    ))
                                    print(f"[BOM FIX] Renamed `{col_name}` -> `{clean_name}` in table `{table}`")
                                elif flavor == "postgresql":
                                    conn.execute(text(
                                        f'ALTER TABLE "{table}" RENAME COLUMN "{col_name}" TO "{clean_name}"'
                                    ))
                                    print(f"[BOM FIX] Renamed `{col_name}` -> `{clean_name}` in table `{table}`")
                            except Exception as rename_err:
                                print(f"[BOM FIX WARNING] Could not rename column `{col_name}`: {rename_err}")
        except Exception:
            pass  # Never break startup on BOM fix failure

    def get_dataset_preview(self, dataset_id: str) -> list:
        """
        Retrieves first 20 rows of a dataset utilizing a file cache or lazy loaders.
        """
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise ValueError("Dataset not found.")
            
        os.makedirs(PREVIEWS_DIR, exist_ok=True)
        preview_cache_path = os.path.join(PREVIEWS_DIR, f"{dataset_id}_preview.json")
        
        # Load from preview cache
        if os.path.exists(preview_cache_path):
            try:
                with open(preview_cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
                
        preview_data = []
        if row["type"] == "file":
            filepath = os.path.join(DATA_DIR, row["filename"])
            ext = os.path.splitext(row["filename"])[1].lower()
            if ext == ".csv":
                df = pd.read_csv(filepath, nrows=20)
            else:
                df = pd.read_excel(filepath, nrows=20)
            
            # Convert timestamp columns
            for c in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[c]):
                    df[c] = df[c].astype(str)
            preview_data = df.to_dict(orient="records")
        else:
            # SQL preview
            creds = self.decrypt_credentials(row["connection_info"])
            from backend.services.loader import create_db_engine
            engine_obj, _ = create_db_engine(
                db_type=row["source"].lower(),
                sqlite_path=creds.get("sqlite_path"),
                host=creds.get("host", "localhost"),
                port=creds.get("port"),
                db_name=creds.get("db_name", ""),
                username=creds.get("username", ""),
                password=creds.get("password", "")
            )
            inspector = inspect(engine_obj)
            tables = inspector.get_table_names()
            if tables:
                # Fetch first table's preview
                df = pd.read_sql(f"SELECT * FROM {tables[0]} LIMIT 20", engine_obj)
                preview_data = df.to_dict(orient="records")
                
        # Write preview cache
        try:
            with open(preview_cache_path, "w", encoding="utf-8") as f:
                json.dump(preview_data, f, indent=4)
        except Exception:
            pass
            
        return preview_data

    def delete_dataset(self, dataset_id: str):
        """
        Thread-safe deletion of files and registry metadata.
        """
        with dataset_lock:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                return

            was_active = (row["is_active"] == 1)
            filename = row.get("filename")
            ds_type = row.get("type")
            user_id = row.get("user_id")

            # Unload from memory first if loaded
            if row["name"] in config.datasets:
                del config.datasets[row["name"]]
            clear_schema_cache()

            # Delete DB record explicitly FIRST and commit immediately
            cursor.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
            conn.commit()

            # Delete preview cache
            preview_cache_path = os.path.join(PREVIEWS_DIR, f"{dataset_id}_preview.json")
            if os.path.exists(preview_cache_path):
                try: os.remove(preview_cache_path)
                except Exception: pass

            # Delete file on disk safely
            if ds_type == "file" and filename:
                filepath = os.path.join(DATA_DIR, filename)
                if os.path.exists(filepath):
                    try: os.remove(filepath)
                    except Exception: pass

            # If the deleted dataset was active, activate the next available dataset (excluding deleted ID!)
            if was_active:
                if user_id:
                    cursor.execute("SELECT id FROM datasets WHERE id != ? AND (user_id = ? OR user_id IS NULL) ORDER BY upload_time DESC LIMIT 1", (dataset_id, user_id))
                else:
                    cursor.execute("SELECT id FROM datasets WHERE id != ? ORDER BY upload_time DESC LIMIT 1", (dataset_id,))
                another = cursor.fetchone()
                conn.close()

                if another:
                    self.activate_dataset_by_id(another["id"], user_id=user_id)
                else:
                    config.datasets.clear()
                    config.database_engine = None
            else:
                conn.close()

            gc.collect()

    def rename_dataset(self, dataset_id: str, new_name: str):
        """
        Renames a dataset.
        """
        with dataset_lock:
            normalized_name = new_name.strip().lower().replace(" ", "_")
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE datasets SET name = ? WHERE id = ?", (normalized_name, dataset_id))
            conn.commit()
            conn.close()

    def clear_all_datasets(self):
        with dataset_lock:
            self.clear_all_datasets_unsafe()

    def clear_all_datasets_unsafe(self):
        """
        Resets registry tables, cache directories and unloads RAM.
        """
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM datasets WHERE type = 'file'")
        files = cursor.fetchall()
        for f in files:
            p = os.path.join(DATA_DIR, f["filename"])
            if os.path.exists(p):
                try: os.remove(p)
                except Exception: pass
                
        cursor.execute("DELETE FROM datasets")
        cursor.execute("DELETE FROM messages")
        cursor.execute("UPDATE conversations SET summary = NULL, dataset_id = NULL")
        conn.commit()
        conn.close()
        
        # Clear previews folder
        if os.path.exists(PREVIEWS_DIR):
            import shutil
            try: shutil.rmtree(PREVIEWS_DIR)
            except Exception: pass
            
        config.datasets.clear()
        config.database_engine = None
        clear_schema_cache()
        gc.collect()

    def run_background_profiler(self, name: str, dataset_id: str):
        """
        Asynchronously profiles datasets and writes metrics values.
        """
        try:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return
                
            # Generate profile
            filepath = os.path.join(DATA_DIR, row["filename"])
            df = pd.read_csv(filepath) if row["filename"].endswith(".csv") else pd.read_excel(filepath)
            
            # Triggers profiler calculations
            from backend.services.schema_cache import get_table_profile
            get_table_profile(name)
            
            # Save health metrics updates
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE datasets SET status = 'active' WHERE id = ?", (dataset_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[BACKGROUND PROFILER ERROR] {str(e)}")
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE datasets SET status = 'error' WHERE id = ?", (dataset_id,))
            conn.commit()
            conn.close()

    def load_active_dataset_on_startup(self):
        """
        Finds the active dataset and loads it into config.datasets.
        """
        try:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM datasets WHERE is_active = 1 LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            if row:
                self.activate_dataset_by_id(row["id"])
        except Exception as e:
            print(f"[STARTUP ACTIVATION WARNING] {str(e)}")
