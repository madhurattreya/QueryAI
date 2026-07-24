"""
backend/main.py
────────────────
FastAPI application entry point.

Changes from v1:
  - Removed duplicate observability_router import and registration (was on lines 28 + 91)
  - Added X-Request-ID middleware for request tracing
  - Added global structured exception handler
  - Integrated StartupValidator in lifespan
  - CORS origins now read from config (FRONTEND_URL env var)
"""
import uuid
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import backend.config as config
from backend.services.loader import load_default_datasets

# ─── Router imports ───────────────────────────────────────────────────────────
from backend.routers.settings import router as settings_router
from backend.routers.upload import router as upload_router
from backend.routers.sql import router as sql_router
from backend.routers.query import router as query_router
from backend.routers.insights import router as insights_router
from backend.routers.observability import router as observability_router   # imported ONCE
from backend.routers.datasets import router as datasets_router
from backend.routers.relationships import router as relationships_router
from backend.routers.semantic_model import router as semantic_model_router
from backend.routers.dashboards import router as dashboards_router
from backend.routers.scheduler import router as scheduler_router
from backend.routers.alerts import router as alerts_router
from backend.routers.forecasting import router as forecasting_router
from backend.routers.security import router as security_router
from backend.routers.collaboration import router as collaboration_router
from backend.routers.search import router as search_router
from backend.routers.health import router as health_router
from backend.routers.export import router as export_router
from backend.routers.auth import router as auth_router
from backend.routers.workspace import router as workspace_router
from backend.routers.api_mgmt import router as api_mgmt_router
from backend.routers.semantic_sync import router as semantic_sync_router



# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup sequence:
      1. Load active dataset from registry
      2. Start scheduler
      3. Start alert engine
      4. Run startup validation checks (non-fatal)
    """
    # 1. Dataset
    try:
        from backend.services.dataset_manager import DatasetManager
        DatasetManager().load_active_dataset_on_startup()
    except Exception:
        pass

    # 2. Scheduler
    try:
        from backend.services.scheduler import SchedulerService
        SchedulerService().start_scheduler()
    except Exception:
        pass

    # 3. Alert engine
    try:
        from backend.services.alert_engine import AlertEngineService
        AlertEngineService().start_alerts_engine()
    except Exception:
        pass

    # 4. Startup validation (non-fatal)
    try:
        from backend.services.startup_validator import StartupValidator
        StartupValidator().run_all_checks()
    except Exception as e:
        print(f"[STARTUP WARN] Startup validator failed: {e}")

    yield
    # Shutdown — nothing required yet


# ─── App factory ──────────────────────────────────────────────────────────────

# Global rate limiter instance (keyed by client IP)
_limiter = Limiter(key_func=get_remote_address)

is_prod = config.app_settings.environment.lower() == "production"

app = FastAPI(
    title="QueryIQ Enterprise AI Data Analytics Platform",
    version=config.app_settings.app_version,
    description="Natural-language analytics over your data.",
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
    openapi_url=None if is_prod else "/openapi.json",
    lifespan=lifespan,
)

# Register rate limiter state and 429 handler
app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ─── Middleware: Request ID ────────────────────────────────────────────────────

import os
from fastapi.middleware.trustedhost import TrustedHostMiddleware

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """
    Attaches a unique X-Request-ID to every request and response.
    Useful for correlating logs, debug_info, and error traces.
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ─── Middleware: Security Headers & CSP ───────────────────────────────────────

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # HSTS: 1 Year protection
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Allow iframe rendering for chart endpoints (/api/chart/html and /chart/html)
    path = request.url.path
    if "/chart/" in path or path.startswith("/api/chart"):
        if "X-Frame-Options" in response.headers:
            del response.headers["X-Frame-Options"]
        response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' https: cdn.plot.ly; script-src 'self' 'unsafe-inline' https: cdn.plot.ly; style-src 'self' 'unsafe-inline' https:;"
    else:
        # Anti Clickjacking for standard API endpoints
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # XSS Protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # MIME Sniffing protection
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Content Security Policy
        response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' https:; script-src 'self' 'unsafe-inline' https: cdn.plot.ly; style-src 'self' 'unsafe-inline' https:;"
    return response


# ─── Middleware: Observability Logging ────────────────────────────────────────

@app.middleware("http")
async def add_observability_logging(request: Request, call_next):
    t_start = time.time()
    response = await call_next(request)
    duration = time.time() - t_start
    
    request_id = getattr(request.state, "request_id", "unknown")
    workspace_id = request.headers.get("x-workspace-id", "none")
    user = "anonymous"
    
    # Read user context from Authorization JWT Header if present
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            from backend.services.security_manager import decode_jwt
            payload = decode_jwt(token)
            user = payload.get("username", "anonymous")
        except Exception:
            pass
            
    from backend.services.logger import log_info
    log_info(
        f"HTTP Request: path={request.url.path} | request_id={request_id} | user={user} | "
        f"workspace={workspace_id} | duration={duration*1000:.2f}ms | status={response.status_code}"
    )
    return response


# ─── Middleware: CORS ─────────────────────────────────────────────────────────

_frontend_url = config.app_settings.frontend_url
_is_production = config.app_settings.environment.lower() == "production"

# In production, only allow the configured FRONTEND_URL.
# In development, also allow localhost origins for convenience.
if _is_production:
    allowed_origins = [_frontend_url]
    allow_origin_regex = None
else:
    allowed_origins = list(dict.fromkeys([
        _frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]))
    allow_origin_regex = r"http://(localhost|127\.0\.0\.1)(:\d+)?"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# ─── Middleware: Trusted Host ────────────────────────────────────────────────
# Production: Set ALLOWED_HOSTS env var to your domain (e.g. "example.com,www.example.com")
# Development: Defaults to localhost only.
_allowed_hosts_default = "localhost,127.0.0.1,*.localhost" if not _is_production else "*"
_allowed_hosts = os.environ.get("ALLOWED_HOSTS", _allowed_hosts_default).split(",")

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_allowed_hosts,
)


# ─── Global exception handler ────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catches any unhandled exception and returns a structured JSON error
    instead of a raw 500 traceback. Preserves request_id for tracing.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    error_detail = str(exc)
    tb = traceback.format_exc()
    print(f"[ERROR] request_id={request_id} | {error_detail}\n{tb}")

    # Map known exception types to user-friendly error codes
    from backend.services.llm import LLMTimeoutError, LLMUnavailableError
    if isinstance(exc, LLMTimeoutError):
        error_code = "LLM_TIMEOUT"
        status_code = 504
        user_message = (
            "The AI model took too long to respond. "
            "Please try again or switch to a faster model in Settings."
        )
    elif isinstance(exc, LLMUnavailableError):
        error_code = "LLM_UNAVAILABLE"
        status_code = 503
        user_message = "All AI models are currently unavailable. Please check Ollama is running."
    else:
        error_code = "INTERNAL_ERROR"
        status_code = 500
        user_message = "An unexpected server error occurred. Please try again."

    # In production, suppress internal error details to avoid leaking stack traces.
    # In development, expose the full detail for easier debugging.
    is_prod = config.app_settings.environment.lower() == "production"
    response_content = {
        "error_code": error_code,
        "message": user_message,
        "request_id": request_id,
    }
    if not is_prod:
        response_content["detail"] = error_detail

    return JSONResponse(status_code=status_code, content=response_content)


# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(settings_router)
app.include_router(upload_router)
app.include_router(sql_router)
app.include_router(query_router)
app.include_router(insights_router)
app.include_router(observability_router)    # registered ONCE (was registered twice)
app.include_router(datasets_router)
app.include_router(relationships_router)
app.include_router(semantic_model_router)
app.include_router(dashboards_router)
app.include_router(scheduler_router)
app.include_router(alerts_router)
app.include_router(forecasting_router)
app.include_router(security_router)
app.include_router(collaboration_router)
app.include_router(search_router)
app.include_router(health_router)
app.include_router(export_router)
app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(api_mgmt_router)
app.include_router(semantic_sync_router)



# ─── Root ─────────────────────────────────────────────────────────────────────

@app.get("/")
def read_root():
    return {
        "message": "QueryIQ Enterprise AI Data Analytics Platform",
        "version": config.app_settings.app_version,
        "docs": "/docs",
        "health": "/api/health",
    }
