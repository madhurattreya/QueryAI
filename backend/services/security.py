import ast
import re

def validate_code(code_str: str):
    """
    Parses the generated code string using Python's ast module and inspects the nodes
    to ensure it doesn't perform unsafe operations.
    """
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in generated code: {e}")

    # Blocked function/attribute names
    blocked_calls = {
        'eval', 'exec', 'compile', 'open', '__import__', 
        'getattr', 'setattr', 'delattr', 'globals', 'locals', 
        'quit', 'exit'
    }
    blocked_attributes = {
        'os', 'sys', 'subprocess', 'shutil', 'socket', 
        'requests', 'pathlib', 'builtins', 'importlib'
    }

    for node in ast.walk(tree):
        # 1. Disallow imports completely
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Unsafe code detected: imports are not allowed in queries.")
            
        # 2. Disallow loops to prevent infinite execution / resource denial
        if isinstance(node, (ast.While, ast.For)):
            raise ValueError("Unsafe code detected: loops are not allowed in queries.")
            
        # 3. Disallow function/class definitions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            raise ValueError("Unsafe code detected: function or class definitions are not allowed.")
            
        # 4. Disallow lambda expressions
        if isinstance(node, ast.Lambda):
            raise ValueError("Unsafe code detected: lambda expressions are not allowed.")
            
        # 5. Disallow try/except blocks
        if isinstance(node, ast.Try):
            raise ValueError("Unsafe code detected: try/except blocks are not allowed.")
            
        # 6. Disallow with, delete, global, and nonlocal statements
        if isinstance(node, (ast.With, ast.Delete, ast.Global, ast.Nonlocal)):
            raise ValueError("Unsafe code detected: with, delete, global, or nonlocal statements are not allowed.")
            
        # 7. Disallow magic attributes (starting with "__") and dangerous system module accesses
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                raise ValueError("Unsafe code detected: magic attributes starting with '__' are not allowed.")
            if isinstance(node.value, ast.Name) and node.value.id in blocked_attributes:
                raise ValueError(f"Unsafe code detected: Access to blocked module '{node.value.id}' is not allowed.")
                
        # 8. Disallow dangerous built-in function calls
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                if func.id in blocked_calls:
                    raise ValueError(f"Unsafe code detected: Call to blocked function '{func.id}' is not allowed.")
            elif isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name) and func.value.id in blocked_attributes:
                    raise ValueError(f"Unsafe code detected: Call to blocked module '{func.value.id}' is not allowed.")
                    
    return True

def validate_sql(query_str: str):
    """
    Validates that the SQL query is a SELECT statement and does not contain destructive keywords.
    """
    clean_query = query_str.strip().lower()
    
    # Strip comment lines
    lines = [line.strip() for line in clean_query.split("\n")]
    lines = [line for line in lines if line and not line.startswith("--") and not line.startswith("#")]
    if not lines:
        raise ValueError("Empty query generated.")
        
    first_word = lines[0].split()[0]
    if first_word != "select":
        raise ValueError("Only SELECT queries are allowed for security reasons.")
        
    # Check for forbidden keywords (e.g. drop, truncate)
    forbidden_keywords = {"insert", "update", "delete", "drop", "alter", "truncate", "create", "grant", "revoke", "replace"}
    
    # Strip brackets, parentheses, semicolons, commas
    clean_query_normalized = re.sub(r'[\(\),;]', ' ', clean_query)
    words = set(clean_query_normalized.split())
    found_forbidden = words.intersection(forbidden_keywords)
    if found_forbidden:
        raise ValueError(f"Security block: Forbidden SQL keyword(s) detected: {', '.join(found_forbidden)}")
        
    return True

# ----------------- RBAC & Audit Logging -----------------
import uuid
import backend.services.history_db as db

# Role permission registry
ROLE_PERMISSIONS = {
    "Admin": {"view_dataset", "edit_dataset", "delete_dataset", "create_measure", "create_dashboard", "edit_dashboard", "delete_dashboard", "scheduler_reports"},
    "Analyst": {"view_dataset", "create_measure", "create_dashboard", "edit_dashboard", "delete_dashboard"},
    "Viewer": {"view_dataset"}
}

def check_permission(role: str, action: str) -> bool:
    """
    Checks if a role is permitted to perform a specific action.
    """
    allowed_actions = ROLE_PERMISSIONS.get(role, set())
    if action in allowed_actions:
        return True
    return False

def log_audit_action(username: str, action: str, details: str):
    """
    Saves security actions & query runs to SQLite audit log.
    """
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_logs (id, username, action, details)
            VALUES (?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), username, action, details)
        )
        conn.commit()
        conn.close()
        print(f"[AUDIT LOG] {username} performed action: '{action}' ({details})")
    except Exception as e:
        print(f"[AUDIT LOG WARNING] Logging failed: {e}")

