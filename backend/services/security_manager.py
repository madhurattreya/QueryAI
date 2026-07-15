import time
import uuid
import hmac
import hashlib
import base64
import json
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import backend.config as config
import os

# Dynamic secret loaded from centralized app settings
JWT_SECRET = config.app_settings.jwt_secret
security_scheme = HTTPBearer(auto_error=False)

# Password Hashing Utilities (Production Bcrypt with Secure PBKDF2 Fallback)
try:
    import bcrypt
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    def verify_password(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())
except ImportError:
    def hash_password(password: str) -> str:
        # Secure random bytes salt to prevent predictability
        salt = base64.b64encode(os.urandom(16)).decode()
        # 600,000 iterations following OWASP recommendations
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000)
        return f"{salt}${dk.hex()}"
    def verify_password(password: str, hashed: str) -> bool:
        try:
            salt, dk_hex = hashed.split("$")
            dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000)
            return hmac.compare_digest(dk.hex(), dk_hex)
        except Exception:
            return False

# Pure-Python JWT Implementation
def create_jwt(payload: dict, expires_in_seconds: int = 3600) -> str:
    p = payload.copy()
    p["exp"] = int(time.time()) + expires_in_seconds
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(p).encode()).decode().rstrip("=")
    msg = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(JWT_SECRET, msg, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def decode_jwt(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Token must have 3 segments")
        header_b64, payload_b64, sig_b64 = parts
        msg = f"{header_b64}.{payload_b64}".encode()
        
        # Base64 padding correction
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)).decode())
        
        # Verify signature
        expected_sig = hmac.new(JWT_SECRET, msg, hashlib.sha256).digest()
        actual_sig = base64.urlsafe_b64decode(sig_b64 + "=" * ((4 - len(sig_b64) % 4) % 4))
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Signature mismatch")
            
        if payload.get("exp", 0) < time.time():
            raise ValueError("Token expired")
            
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired credentials: {e}")

# Enterprise RBAC Matrix
# Format: { Role: { Allowed Permissions } }
ROLE_PERMISSIONS = {
    "Super Admin": {
        "dataset_access", "dashboard_creation", "dashboard_editing", 
        "sql_execution", "export", "delete", "user_management", "api_access", "workspace"
    },
    "Admin": {
        "dataset_access", "dashboard_creation", "dashboard_editing", 
        "sql_execution", "export", "delete", "user_management", "workspace"
    },
    "Manager": {
        "dataset_access", "dashboard_creation", "dashboard_editing", 
        "export", "workspace"
    },
    "Analyst": {
        "dataset_access", "dashboard_creation", "dashboard_editing", 
        "export"
    },
    "Viewer": {
        "dataset_access", "export"
    }
}

def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)) -> dict:
    """
    FastAPI dependency to verify authorization headers and return the token payload.
    In development mode, returns a mock admin user if no token is provided.
    """
    if not credentials or not credentials.credentials:
        if config.app_settings.environment.lower() != "production":
            return {"user_id": "dev_id", "username": "dev_user", "role": "Super Admin"}
        raise HTTPException(
            status_code=401,
            detail="Access Denied: Authorization token is missing."
        )
    return decode_jwt(credentials.credentials)

def check_permission(user_role: str, permission: str) -> bool:
    """
    Validates if a specific user role possesses the required permission.
    """
    allowed = ROLE_PERMISSIONS.get(user_role, set())
    return permission in allowed

def get_current_user_with_permission(permission: str):
    """
    FastAPI dependency factory that returns user payload after checking permissions.
    """
    def dependency(user: dict = Depends(verify_token)) -> dict:
        role = user.get("role", "Viewer")
        if not check_permission(role, permission):
            raise HTTPException(
                status_code=403, 
                detail=f"Access Denied: Role '{role}' does not have '{permission}' permission."
            )
        return user
    return dependency
