from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import uuid
import time
import re
import backend.services.history_db as db
from backend.services.security_manager import hash_password, verify_password, create_jwt

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+")

class UserRegister(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

@router.post("/signup")
def signup(payload: UserRegister):
    if not EMAIL_REGEX.match(payload.email):
        raise HTTPException(status_code=400, detail="Invalid email format.")
        
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Check if username or email exists
    cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (payload.username, payload.email))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username or email already registered.")

    # Check if first user in database (Super Admin)
    cursor.execute("SELECT count(*) as count FROM users")
    count = cursor.fetchone()["count"]
    role = "Super Admin" if count == 0 else "Viewer"

    hashed = hash_password(payload.password)
    user_id = str(uuid.uuid4())

    cursor.execute(
        """
        INSERT INTO users (id, username, email, password_hash, role, is_verified)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (user_id, payload.username, payload.email, hashed, role)
    )
    conn.commit()
    conn.close()
    
    # Audit Log
    from backend.services.security import log_audit_action
    log_audit_action(payload.username, "User Signup", f"Registered successfully with role {role}")

    return {"status": "success", "message": "User registered successfully", "role": role}


@router.post("/login")
def login(payload: UserLogin):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (payload.username,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid username or password.")
        
    if not verify_password(payload.password, user["password_hash"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    # Create Access & Refresh Token
    token_payload = {
        "user_id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"]
    }
    access_token = create_jwt(token_payload, expires_in_seconds=3600)
    refresh_token = str(uuid.uuid4())

    # Save refresh token in DB
    cursor.execute("UPDATE users SET refresh_token = ? WHERE id = ?", (refresh_token, user["id"]))
    conn.commit()
    conn.close()

    # Audit Log
    from backend.services.security import log_audit_action
    log_audit_action(user["username"], "User Login", "Logged in via local credentials")

    return {
        "status": "success",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"]
        }
    }


@router.post("/refresh")
def refresh(payload: TokenRefreshRequest):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE refresh_token = ?", (payload.refresh_token,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")
        
    token_payload = {
        "user_id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"]
    }
    new_access_token = create_jwt(token_payload, expires_in_seconds=3600)
    conn.close()
    return {"status": "success", "access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout")
def logout(username: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET refresh_token = NULL WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    
    from backend.services.security import log_audit_action
    log_audit_action(username, "User Logout", "Logged out successfully")
    return {"status": "success", "message": "Logged out successfully"}


@router.post("/reset-password/request")
def request_password_reset(payload: PasswordResetRequest):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE email = ?", (payload.email,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        # Prevent user enumeration by returning success regardless
        return {"status": "success", "message": "Password reset token sent if email registered"}
        
    reset_token = str(uuid.uuid4())
    cursor.execute("UPDATE users SET reset_token = ? WHERE id = ?", (reset_token, user["id"]))
    conn.commit()
    conn.close()
    
    from backend.services.security import log_audit_action
    log_audit_action(user["username"], "Reset Requested", "Generated password reset link/token")

    return {"status": "success", "message": "Password reset token sent", "debug_token": reset_token}


@router.post("/reset-password/confirm")
def confirm_password_reset(payload: PasswordResetConfirm):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE reset_token = ?", (payload.token,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid reset token.")
        
    hashed = hash_password(payload.new_password)
    cursor.execute("UPDATE users SET password_hash = ?, reset_token = NULL WHERE id = ?", (hashed, user["id"]))
    conn.commit()
    conn.close()
    
    from backend.services.security import log_audit_action
    log_audit_action(user["username"], "Reset Confirmed", "Password successfully changed via reset token")

    return {"status": "success", "message": "Password changed successfully"}


@router.get("/oauth/{provider}")
def oauth_login(provider: str, email: str = "oauth_user@example.com", username: str = "oauth_user"):
    """
    Mock OAuth implementation for Google, Microsoft Azure, and GitHub.
    """
    if provider not in ["google", "microsoft", "github"]:
        raise HTTPException(status_code=400, detail=f"Unsupported OAuth provider: {provider}")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Fetch or register OAuth user
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    
    if not user:
        user_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO users (id, username, email, password_hash, role, is_verified)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (user_id, f"{username}_{provider}", email, "oauth_mocked_password_hash", "Viewer")
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
    token_payload = {
        "user_id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"]
    }
    access_token = create_jwt(token_payload, expires_in_seconds=3600)
    conn.close()

    from backend.services.security import log_audit_action
    log_audit_action(user["username"], "OAuth Login", f"Authenticated via OAuth provider: {provider}")

    return {
        "status": "success",
        "access_token": access_token,
        "token_type": "bearer",
        "user": token_payload
    }
