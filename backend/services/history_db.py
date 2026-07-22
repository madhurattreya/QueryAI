import os
import sqlite3
import uuid
from datetime import datetime
from backend.services.loader import DATA_DIR

import backend.config as config

DB_FILE = os.path.join(DATA_DIR, "studio_metadata.db")


class PostgresCursorWrapper:
    def __init__(self, pg_cursor):
        self._cursor = pg_cursor
        self.db_type = "postgres"

    def execute(self, query: str, params=None):
        query_pg = query.replace("?", "%s")
        if "julianday('now') - julianday(created_at)" in query_pg:
            query_pg = query_pg.replace(
                "julianday('now') - julianday(created_at)",
                "EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400.0"
            )
        if params:
            self._cursor.execute(query_pg, params)
        else:
            self._cursor.execute(query_pg)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PostgresConnWrapper:
    def __init__(self, pg_conn):
        self._conn = pg_conn
        self.db_type = "postgres"

    def cursor(self):
        import psycopg2.extras
        return PostgresCursorWrapper(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))

    def execute(self, query: str, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


class MysqlCursorWrapper:
    def __init__(self, mysql_cursor):
        self._cursor = mysql_cursor
        self.db_type = "mysql"

    def execute(self, query: str, params=None):
        query_mysql = query.replace("?", "%s")
        # Auto-escape MySQL reserved keywords: rows, columns, condition
        import re
        query_mysql = re.sub(r'\b(rows|columns|condition)\b', r'`\1`', query_mysql, flags=re.IGNORECASE)
        
        # MySQL DDL compatibility for TEXT primary keys, foreign keys, and defaults
        if query_mysql.strip().upper().startswith("CREATE TABLE"):
            query_mysql = re.sub(r'\bTEXT\s+PRIMARY\s+KEY\b', 'VARCHAR(255) PRIMARY KEY', query_mysql, flags=re.IGNORECASE)
            query_mysql = re.sub(r'\bTEXT\s+UNIQUE\b', 'VARCHAR(255) UNIQUE', query_mysql, flags=re.IGNORECASE)
            query_mysql = re.sub(r'\bTEXT\s+DEFAULT\b', 'VARCHAR(255) DEFAULT', query_mysql, flags=re.IGNORECASE)
            query_mysql = re.sub(r'(\b\w+_id\b|\b\w+_key\b|\bid\b|\brole\b|\busername\b|\bemail\b|\bsource\b|\btype\b|\bstatus\b|\bfilename\b|\bhash\b|\bchart_type\b|\bhtml_path\b|\bpng_path\b|\bresult_file\b|\bchart_id\b|\bname\b)\s+TEXT\b', r'\1 VARCHAR(255)', query_mysql, flags=re.IGNORECASE)
        
        if "julianday('now') - julianday(created_at)" in query_mysql:
            query_mysql = query_mysql.replace(
                "julianday('now') - julianday(created_at)",
                "TIMESTAMPDIFF(SECOND, created_at, NOW()) / 86400.0"
            )
        if query_mysql.strip().upper().startswith("CREATE INDEX"):
            query_mysql = query_mysql.replace(" IF NOT EXISTS", "").replace(" if not exists", "")
            try:
                self._cursor.execute(query_mysql, params)
            except Exception:
                pass
            return self

        if params:
            self._cursor.execute(query_mysql, params)
        else:
            self._cursor.execute(query_mysql)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [dict(r) for r in rows]

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class MysqlConnWrapper:
    def __init__(self, mysql_conn):
        self._conn = mysql_conn
        self.db_type = "mysql"

    def cursor(self):
        import pymysql.cursors
        return MysqlCursorWrapper(self._conn.cursor(pymysql.cursors.DictCursor))

    def execute(self, query: str, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_db_connection():
    db_url = config.app_settings.database_url
    if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
        try:
            import psycopg2
            pg_conn = psycopg2.connect(db_url)
            pg_conn.autocommit = False
            return PostgresConnWrapper(pg_conn)
        except Exception as e:
            # Fallback to local SQLite if Postgres is unreachable
            print(f"[DB WARN] Could not connect to PostgreSQL ({e}). Falling back to local SQLite.")

    elif db_url.startswith("mysql://") or db_url.startswith("mysql+pymysql://"):
        try:
            import urllib.parse
            import pymysql
            url_clean = db_url.replace("mysql+pymysql://", "mysql://")
            parsed = urllib.parse.urlparse(url_clean)
            mysql_conn = pymysql.connect(
                host=parsed.hostname or "localhost",
                port=parsed.port or 3306,
                user=parsed.username or "root",
                password=parsed.password or "",
                database=parsed.path.lstrip("/"),
                autocommit=False
            )
            return MysqlConnWrapper(mysql_conn)
        except Exception as e:
            # Fallback to local SQLite if MySQL is unreachable
            print(f"[DB WARN] Could not connect to MySQL ({e}). Falling back to local SQLite.")

    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Helper to add columns idempotently
    def add_col(table, col, col_type):
        active_type = getattr(cursor, "db_type", "sqlite")
        if active_type == "postgres":
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}")
                return
            except Exception:
                pass
        elif active_type == "mysql":
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                return
            except Exception:
                pass
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = [r['name'] for r in cursor.fetchall()]
            if col not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except Exception:
            pass
            pass

    # 1. Create datasets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS datasets (
        id TEXT PRIMARY KEY,
        name TEXT,
        filename TEXT,
        source TEXT,
        type TEXT,
        hash TEXT,
        rows INTEGER,
        columns INTEGER,
        size_bytes INTEGER,
        is_active INTEGER DEFAULT 0,
        status TEXT DEFAULT 'inactive',
        connection_info TEXT,
        upload_time TIMESTAMP,
        last_used_time TIMESTAMP,
        total_queries INTEGER DEFAULT 0,
        last_query_time TIMESTAMP,
        avg_query_time REAL DEFAULT 0.0,
        cache_hit_rate REAL DEFAULT 0.0,
        charts_generated INTEGER DEFAULT 0
    )
    """)
    
    # 2. Create conversations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        title TEXT,
        summary TEXT,
        dataset_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 3. Create messages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT,
        role TEXT,
        content TEXT,
        generated_code TEXT,
        result_preview TEXT,
        result_file TEXT,
        chart_id TEXT,
        execution_time REAL,
        rows INTEGER,
        prompt_size INTEGER,
        engine_used TEXT,
        debug_info TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    )
    """)
    
    # 4. Create charts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS charts (
        id TEXT PRIMARY KEY,
        conversation_id TEXT,
        message_id TEXT,
        dataset_id TEXT,
        question TEXT,
        chart_type TEXT,
        html_path TEXT,
        png_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
        FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
    )
    """)
    
    # 5. Create relationships table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS relationships (
        id TEXT PRIMARY KEY,
        source_dataset_id TEXT,
        source_column TEXT,
        target_dataset_id TEXT,
        target_column TEXT,
        relationship_type TEXT,
        is_user_defined INTEGER DEFAULT 0,
        confidence REAL DEFAULT 1.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 6. Create semantic_model table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS semantic_model (
        id TEXT PRIMARY KEY,
        dataset_id TEXT,
        name TEXT,
        type TEXT,
        expression TEXT,
        definition TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    add_col("semantic_model", "display_name", "TEXT")
    add_col("semantic_model", "description", "TEXT")
    add_col("semantic_model", "business_meaning", "TEXT")
    add_col("semantic_model", "synonyms", "TEXT")
    add_col("semantic_model", "units", "TEXT")
    add_col("semantic_model", "aggregation", "TEXT")
    add_col("semantic_model", "category", "TEXT")
    add_col("semantic_model", "is_measure", "INTEGER DEFAULT 0")
    add_col("semantic_model", "is_dimension", "INTEGER DEFAULT 0")
    add_col("semantic_model", "hierarchy", "TEXT")
    
    # 7. Create dashboards table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dashboards (
        id TEXT PRIMARY KEY,
        title TEXT,
        layout TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 8. Create scheduler_jobs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheduler_jobs (
        id TEXT PRIMARY KEY,
        dashboard_id TEXT,
        cron_expression TEXT,
        export_format TEXT,
        email_recipient TEXT,
        last_run_time TIMESTAMP,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 9. Create alerts table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY,
        dataset_id TEXT,
        metric_column TEXT,
        condition TEXT,
        threshold_value REAL,
        email_recipient TEXT,
        last_checked_time TIMESTAMP,
        triggered INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 10. Create audit_logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        username TEXT,
        action TEXT,
        details TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 11. Create comments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id TEXT PRIMARY KEY,
        dashboard_id TEXT,
        username TEXT,
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 12. Create favorites table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS favorites (
        id TEXT PRIMARY KEY,
        username TEXT,
        query TEXT,
        title TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 13. Create telemetry_logs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_logs (
        id TEXT PRIMARY KEY,
        metric_name TEXT,
        metric_value REAL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 14. Create users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password_hash TEXT,
        role TEXT,
        is_verified INTEGER DEFAULT 0,
        reset_token TEXT,
        refresh_token TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 15. Create workspaces table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 16. Create workspace_members table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workspace_members (
        id TEXT PRIMARY KEY,
        workspace_id TEXT,
        user_id TEXT,
        role TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 17. Create dashboard_versions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dashboard_versions (
        id TEXT PRIMARY KEY,
        dashboard_id TEXT,
        version_number INTEGER,
        author TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        change_description TEXT,
        status TEXT DEFAULT 'Draft',
        layout TEXT,
        FOREIGN KEY(dashboard_id) REFERENCES dashboards(id) ON DELETE CASCADE
    )
    """)

    # 18. Create scheduler_history table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scheduler_history (
        id TEXT PRIMARY KEY,
        job_id TEXT,
        report_name TEXT,
        status TEXT,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        duration REAL,
        error_message TEXT,
        retry_count INTEGER DEFAULT 0
    )
    """)

    # 19. Create notifications table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        username TEXT,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 20. Create api_keys table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        key_hash TEXT UNIQUE,
        username TEXT,
        permissions TEXT,
        workspace_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Migrations for datasets table
    for col, col_type in [
        ("filename", "TEXT"),
        ("rows", "INTEGER"),
        ("columns", "INTEGER"),
        ("size_bytes", "INTEGER"),
        ("is_active", "INTEGER DEFAULT 0"),
        ("status", "TEXT DEFAULT 'inactive'"),
        ("connection_info", "TEXT"),
        ("upload_time", "TIMESTAMP"),
        ("last_used_time", "TIMESTAMP"),
        ("total_queries", "INTEGER DEFAULT 0"),
        ("last_query_time", "TIMESTAMP"),
        ("avg_query_time", "REAL DEFAULT 0.0"),
        ("cache_hit_rate", "REAL DEFAULT 0.0"),
        ("charts_generated", "INTEGER DEFAULT 0"),
        ("date_columns", "TEXT"),
        ("workspace_id", "TEXT")
    ]:
        add_col("datasets", col, col_type)
        
    # Migrations for messages table
    for col, col_type in [
        ("prompt_size", "INTEGER"),
        ("engine_used", "TEXT"),
        ("debug_info", "TEXT")
    ]:
        add_col("messages", col, col_type)

    # Migrations for other tables
    add_col("dashboards", "workspace_id", "TEXT")
    add_col("conversations", "workspace_id", "TEXT")
            
    # Secondary performance indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_dataset_id ON conversations(dataset_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_workspace_id ON conversations(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_charts_message_id ON charts(message_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dashboards_workspace_id ON dashboards(workspace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_username ON audit_logs(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_dashboard_id ON scheduler_jobs(dashboard_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_datasets_workspace_id ON datasets(workspace_id)")

    conn.commit()
    conn.close()

def get_or_create_dataset(name: str, type_str: str = "CSV/Excel", source: str = "local") -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM datasets WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        ds_id = row['id']
    else:
        ds_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO datasets (id, name, source, type, hash) VALUES (?, ?, ?, ?, ?)",
            (ds_id, name, source, type_str, "")
        )
        conn.commit()
    conn.close()
    return ds_id

# Conversations CRUD
def create_conversation(title: str, dataset_id: str = None, workspace_id: str = None) -> str:
    conv_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO conversations (id, title, dataset_id, workspace_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (conv_id, title, dataset_id, workspace_id, datetime.now(), datetime.now())
    )
    conn.commit()
    conn.close()
    return conv_id

def get_conversation(conv_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_conversation(conv_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Delete associated messages
    cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    # Delete associated charts
    cursor.execute("DELETE FROM charts WHERE conversation_id = ?", (conv_id,))
    # Delete conversation itself
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    
    conn.commit()
    conn.close()

def list_conversations(workspace_id: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if workspace_id:
        cursor.execute("SELECT * FROM conversations WHERE workspace_id = ? ORDER BY updated_at DESC", (workspace_id,))
    else:
        cursor.execute("SELECT * FROM conversations ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_conversation_summary(conv_id: str, summary: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE conversations SET summary = ?, updated_at = ? WHERE id = ?",
        (summary, datetime.now(), conv_id)
    )
    conn.commit()
    conn.close()

def update_conversation_title(conv_id: str, title: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, datetime.now(), conv_id)
    )
    conn.commit()
    conn.close()

# Messages CRUD
def add_message(conv_id: str, role: str, content: str, generated_code: str = None, 
                result_preview: str = None, result_file: str = None, chart_id: str = None, 
                execution_time: float = None, rows: int = None, prompt_size: int = None,
                engine_used: str = None, debug_info: str = None) -> str:
    msg_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (id, conversation_id, role, content, generated_code, 
                             result_preview, result_file, chart_id, execution_time, rows,
                             prompt_size, engine_used, debug_info, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (msg_id, conv_id, role, content, generated_code, result_preview, result_file,
          chart_id, execution_time, rows, prompt_size, engine_used, debug_info, datetime.now()))
    
    # Update conversation's updated_at timestamp
    cursor.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (datetime.now(), conv_id))
    
    conn.commit()
    conn.close()
    return msg_id

def get_messages(conv_id: str, limit: int = 5):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC", 
        (conv_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    result = [dict(row) for row in rows]
    if limit:
        return result[-limit:]
    return result

# Charts CRUD
def add_chart(chart_id: str, conv_id: str, msg_id: str, dataset_id: str, question: str, 
              chart_type: str, html_path: str, png_path: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO charts (id, conversation_id, message_id, dataset_id, question, chart_type, html_path, png_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (chart_id, conv_id, msg_id, dataset_id, question, chart_type, html_path, png_path, datetime.now()))
    conn.commit()
    conn.close()

def get_chart(chart_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM charts WHERE id = ?", (chart_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# Full-text Search
def search_conversations(query_str: str):
    """
    Finds conversations matching search terms in messages
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    # Safe SQL like search
    like_query = f"%{query_str}%"
    cursor.execute("""
        SELECT DISTINCT c.* 
        FROM conversations c 
        JOIN messages m ON c.id = m.conversation_id 
        WHERE m.content LIKE ? OR c.title LIKE ?
        ORDER BY c.updated_at DESC
    """, (like_query, like_query))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Cleanup routine
def cleanup_charts(max_age_days: int = 7, max_charts: int = 1000):
    """
    Deletes charts older than max_age_days OR trims total files to max_charts
    """
    charts_dir = os.path.join(DATA_DIR, "charts")
    if not os.path.exists(charts_dir):
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Clean up by age
    cursor.execute("""
        SELECT id, html_path, png_path 
        FROM charts 
        WHERE julianday('now') - julianday(created_at) > ?
    """, (max_age_days,))
    old_charts = cursor.fetchall()
    
    for row in old_charts:
        cid = row['id']
        for p in [row['html_path'], row['png_path']]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except Exception: pass
            # Metadata JSON file
            meta_p = p.replace(".html", "_metadata.json").replace(".png", "_metadata.json") if p else None
            if meta_p and os.path.exists(meta_p):
                try: os.remove(meta_p)
                except Exception: pass
        cursor.execute("DELETE FROM charts WHERE id = ?", (cid,))
        
    # 2. Clean up by count limit
    cursor.execute("SELECT COUNT(*) FROM charts")
    total_count = cursor.fetchone()[0]
    if total_count > max_charts:
        excess = total_count - max_charts
        cursor.execute("""
            SELECT id, html_path, png_path 
            FROM charts 
            ORDER BY created_at ASC 
            LIMIT ?
        """, (excess,))
        excess_charts = cursor.fetchall()
        for row in excess_charts:
            cid = row['id']
            for p in [row['html_path'], row['png_path']]:
                if p and os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass
            cursor.execute("DELETE FROM charts WHERE id = ?", (cid,))
            
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()
