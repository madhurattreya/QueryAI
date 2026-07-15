import os
import re
import pandas as pd
from sqlalchemy import create_engine
import backend.config as config

# Data directory path (absolute to support multiple launch locations)
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))

def normalize_name(s: str) -> str:
    """
    Normalizes file or sheet names to be valid, safe Python variable names.
    """
    s = s.strip().lower()
    s = re.sub(r'[^a-z0-9_]', '_', s)
    s = re.sub(r'_+', '_', s)
    s = s.strip('_')
    if s and s[0].isdigit():
        s = 'data_' + s
    return s or 'dataset'

def load_default_datasets():
    loaded = {}
    if os.path.exists(DATA_DIR) and os.path.isdir(DATA_DIR):
        files = os.listdir(DATA_DIR)
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            name = os.path.splitext(f)[0]
            name_normalized = normalize_name(name)
            if name_normalized == "test_database":
                continue
            filepath = os.path.join(DATA_DIR, f)
            if ext == ".csv":
                try:
                    loaded[name_normalized] = pd.read_csv(filepath)
                    print(f"[LOADED] '{filepath}' -> DataFrame: '{name_normalized}'")
                except Exception as ex:
                    print(f"Error loading {filepath}: {ex}")
            elif ext in [".xlsx", ".xls"]:
                try:
                    xls = pd.ExcelFile(filepath)
                    for sheet in xls.sheet_names:
                        sheet_normalized = normalize_name(sheet)
                        key = f"{name_normalized}_{sheet_normalized}"
                        loaded[key] = pd.read_excel(filepath, sheet_name=sheet)
                        print(f"[LOADED] sheet: '{sheet}' from '{filepath}' -> DataFrame: '{key}'")
                except Exception as ex:
                    print(f"Error loading Excel {filepath}: {ex}")
    return loaded

def create_db_engine(db_type: str, sqlite_path: str = None, host: str = "localhost", port: str = None, db_name: str = "", username: str = "", password: str = ""):
    if db_type == "sqlite":
        if not sqlite_path:
            raise ValueError("SQLite database file path is required.")
        # Make path absolute if relative
        if not os.path.isabs(sqlite_path):
            abs_path = os.path.abspath(os.path.join(DATA_DIR, "..", sqlite_path))
        else:
            abs_path = sqlite_path
        engine = create_engine(f"sqlite:///{abs_path}")
        flavor = "sqlite"
    elif db_type in ["mysql", "postgresql"]:
        if db_type == "mysql":
            port = port or "3306"
            connection_url = f"mysql+pymysql://{username}:{password}@{host}:{port}/{db_name}"
            flavor = "mysql"
        else:
            port = port or "5432"
            connection_url = f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{db_name}"
            flavor = "postgresql"
        from backend.config import app_settings
        pool_kwargs = {}
        if db_type == "postgresql":
            pool_kwargs = {
                "pool_size": app_settings.postgres_pool_size,
                "max_overflow": app_settings.postgres_max_overflow
            }
        engine = create_engine(connection_url, **pool_kwargs)
        # Test connection
        with engine.connect() as conn:
            pass
    else:
        raise ValueError("Unsupported database type.")
    
    return engine, flavor

def setup_data_source():
    """
    Startup interactive wizard to load files or connect to database.
    """
    datasets = {}
    engine = None
    db_flavor = None

    print("============================================================")
    print("                  AI DATA ANALYST SETUP")
    print("============================================================\n")
    print("Select Data Source:")
    print("1. Scan and Load 'data/' folder (Default)")
    print("2. Load a specific CSV / Excel file")
    print("3. Connect to a SQL Database (SQLite, MySQL, PostgreSQL)")
    choice = input("\nEnter choice [1-3] (Default: 1): ").strip()

    if not choice or choice == "1":
        data_dir = DATA_DIR
        if os.path.exists(data_dir) and os.path.isdir(data_dir):
            files = os.listdir(data_dir)
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                name = os.path.splitext(f)[0]
                name_normalized = normalize_name(name)
                filepath = os.path.join(data_dir, f)
                # Ignore temporary db
                if name_normalized == "test_database":
                    continue
                if ext == ".csv":
                    try:
                        datasets[name_normalized] = pd.read_csv(filepath)
                        print(f"[LOADED] '{filepath}' -> DataFrame: '{name_normalized}'")
                    except Exception as ex:
                        print(f"Error loading {filepath}: {ex}")
                elif ext in [".xlsx", ".xls"]:
                    try:
                        xls = pd.ExcelFile(filepath)
                        for sheet in xls.sheet_names:
                            sheet_normalized = normalize_name(sheet)
                            key = f"{name_normalized}_{sheet_normalized}"
                            datasets[key] = pd.read_excel(filepath, sheet_name=sheet)
                            print(f"[LOADED] sheet: '{sheet}' from '{filepath}' -> DataFrame: '{key}'")
                    except Exception as ex:
                        print(f"Error loading Excel {filepath}: {ex}")
        else:
            print("[ERROR] 'data/' directory not found.")
            exit(1)

    elif choice == "2":
        filepath = input("Enter File Path: ").strip()
        filepath = filepath.strip("'\"")
        if os.path.exists(filepath):
            ext = os.path.splitext(filepath)[1].lower()
            name = os.path.splitext(os.path.basename(filepath))[0]
            name_normalized = normalize_name(name)
            if ext == ".csv":
                datasets[name_normalized] = pd.read_csv(filepath)
                print(f"[LOADED] '{filepath}' -> DataFrame: '{name_normalized}'")
            elif ext in [".xlsx", ".xls"]:
                xls = pd.ExcelFile(filepath)
                for sheet in xls.sheet_names:
                    sheet_normalized = normalize_name(sheet)
                    key = f"{name_normalized}_{sheet_normalized}"
                    datasets[key] = pd.read_excel(filepath, sheet_name=sheet)
                    print(f"[LOADED] sheet: '{sheet}' from '{filepath}' -> DataFrame: '{key}'")
            else:
                print("[ERROR] Unsupported file format. Please use CSV or Excel.")
                exit(1)
        else:
            print(f"[ERROR] File not found: {filepath}")
            exit(1)

    elif choice == "3":
        print("\nSelect Database Type:")
        print("1. SQLite (Local File)")
        print("2. MySQL / MariaDB")
        print("3. PostgreSQL")
        db_choice = input("Enter choice [1-3]: ").strip()
        if db_choice == "1":
            db_path = input("Enter SQLite file path (e.g. data/my_db.db): ").strip()
            db_path = db_path.strip("'\"")
            try:
                engine = create_engine(f"sqlite:///{db_path}")
                db_flavor = "sqlite"
                print(f"[SUCCESS] Connected to SQLite database: {db_path}")
            except Exception as ex:
                print(f"Connection failed: {ex}")
                exit(1)
        elif db_choice in ["2", "3"]:
            host = input("Server (Default: localhost): ").strip() or "localhost"
            port = input("Port (Default: 3306 for MySQL, 5432 for Postgres): ").strip()
            db_name = input("Database Name: ").strip()
            user = input("Username: ").strip()
            password = input("Password: ").strip()
            
            if db_choice == "2":
                port = port or "3306"
                connection_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}"
                db_flavor = "mysql"
            else:
                port = port or "5432"
                connection_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"
                db_flavor = "postgresql"
                
            try:
                engine = create_engine(connection_url)
                with engine.connect() as conn:
                    pass
                print(f"[SUCCESS] Connected to {db_flavor} database: {db_name}")
            except Exception as ex:
                print(f"[ERROR] Connection failed: {ex}")
                print("Please ensure database drivers (pymysql, psycopg2) are installed if needed.")
                exit(1)
        else:
            print("[ERROR] Invalid choice.")
            exit(1)
    else:
        print("[ERROR] Invalid choice.")
        exit(1)

    return datasets, engine, db_flavor
