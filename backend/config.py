"""
backend/config.py
─────────────────
Centralized application configuration.

All values are read from `.env` via python-dotenv.
Backward-compatible module-level aliases (datasets, settings, etc.)
are preserved so existing services require zero changes.
"""
import os
import threading
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Load .env on import — override=True ensures .env changes are picked up even
# when the process inherits stale environment variables (e.g. uvicorn --reload).
load_dotenv(override=True)

# ─── Typed configuration accessors ──────────────────────────────────────────

class AppSettings:
    """
    Strongly-typed, validated configuration read from environment variables.
    Provides sensible defaults for every setting.
    """

    # Server
    @property
    def backend_port(self) -> int:
        return int(os.environ.get("BACKEND_PORT", "8000"))

    @property
    def frontend_url(self) -> str:
        return os.environ.get("FRONTEND_URL", "http://localhost:3000")

    @property
    def app_version(self) -> str:
        return os.environ.get("APP_VERSION", "2.0.0")

    # LLM
    @property
    def llm_timeout_seconds(self) -> int:
        val = int(os.environ.get("LLM_TIMEOUT_SECONDS", "35"))
        return max(5, min(val, 300))   # clamp 5–300s

    @property
    def llm_max_retries(self) -> int:
        return max(0, min(int(os.environ.get("LLM_MAX_RETRIES", "1")), 3))

    @property
    def default_model(self) -> str:
        return os.environ.get("DEFAULT_MODEL", "qwen2.5:7b")

    @property
    def ollama_base_url(self) -> str:
        return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

    @property
    def gemini_api_key(self) -> Optional[str]:
        return os.environ.get("GEMINI_API_KEY") or None

    # Engine Routing
    @property
    def confidence_threshold_deterministic(self) -> float:
        return float(os.environ.get("CONFIDENCE_THRESHOLD_DETERMINISTIC", "0.85"))

    @property
    def confidence_threshold_hybrid(self) -> float:
        return float(os.environ.get("CONFIDENCE_THRESHOLD_HYBRID", "0.60"))

    # Cache
    @property
    def query_cache_ttl_seconds(self) -> int:
        return int(os.environ.get("QUERY_CACHE_TTL_SECONDS", "1800"))

    @property
    def schema_cache_ttl_seconds(self) -> int:
        return int(os.environ.get("SCHEMA_CACHE_TTL_SECONDS", "3600"))

    @property
    def query_cache_max_entries(self) -> int:
        return int(os.environ.get("QUERY_CACHE_MAX_ENTRIES", "500"))

    @property
    def conversation_cache_ttl_seconds(self) -> int:
        return int(os.environ.get("CONVERSATION_CACHE_TTL_SECONDS", "900"))

    @property
    def kpi_cache_ttl_seconds(self) -> int:
        return int(os.environ.get("KPI_CACHE_TTL_SECONDS", "1800"))

    # Sandbox Execution
    @property
    def sandbox_timeout_seconds(self) -> int:
        val = int(os.environ.get("SANDBOX_TIMEOUT_SECONDS", "25"))
        return max(5, min(val, 120))  # clamp 5–120s

    @property
    def max_result_rows(self) -> int:
        return int(os.environ.get("MAX_RESULT_ROWS", "10000"))

    @property
    def preview_rows(self) -> int:
        return int(os.environ.get("PREVIEW_ROWS", "15"))

    # Security & Database Settings
    @property
    def jwt_secret(self) -> bytes:
        val = os.environ.get("JWT_SECRET")
        if not val:
            # Fallback for development
            val = "queryiq_super_secret_enterprise_signing_key_998877"
        return val.encode()

    @property
    def jwt_refresh_secret(self) -> bytes:
        val = os.environ.get("JWT_REFRESH_SECRET")
        if not val:
            val = "queryiq_super_secret_refresh_signing_key_778899"
        return val.encode()

    @property
    def database_url(self) -> str:
        return os.environ.get("DATABASE_URL", "sqlite:///studio_metadata.db")

    @property
    def environment(self) -> str:
        return os.environ.get("ENVIRONMENT", "development")

    @property
    def postgres_pool_size(self) -> int:
        return int(os.environ.get("POSTGRES_POOL_SIZE", "5"))

    @property
    def postgres_max_overflow(self) -> int:
        return int(os.environ.get("POSTGRES_MAX_OVERFLOW", "10"))


class DataRegistry:
    """
    Thread-safe registry for in-memory DataFrames.
    Backward-compatible: behaves like a plain dict for all read/write operations.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}

    # ── Dict-like interface ────────────────────────────────────────────────────

    def __getitem__(self, key):
        with self._lock:
            return self._data[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._data[key] = value

    def __delitem__(self, key):
        with self._lock:
            del self._data[key]

    def __contains__(self, key):
        with self._lock:
            return key in self._data

    def __len__(self):
        with self._lock:
            return len(self._data)

    def __iter__(self):
        with self._lock:
            return iter(list(self._data.keys()))

    def items(self):
        with self._lock:
            return list(self._data.items())

    def keys(self):
        with self._lock:
            return list(self._data.keys())

    def values(self):
        with self._lock:
            return list(self._data.values())

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def pop(self, key, *args):
        with self._lock:
            return self._data.pop(key, *args)

    def clear(self):
        with self._lock:
            self._data.clear()

    def update(self, d):
        with self._lock:
            self._data.update(d)


# ─── Singleton instances ─────────────────────────────────────────────────────

app_settings = AppSettings()

# ─── Backward-compatible global state aliases ────────────────────────────────
# All existing services continue to use `config.datasets`, `config.settings`,
# etc. without any changes.

datasets = DataRegistry()          # was: dict — now thread-safe DataRegistry
database_engine = None
db_flavor = None
current_source_type = "file"       # "file" or "sql"

settings: Dict[str, Any] = {
    "model": app_settings.default_model,
    "explain_mode": True,
    "debug_mode": False,
    "fast_mode": False,
    "technical_mode": False,
    "explain_level": "Normal",
}

# Legacy direct key kept for backward compat
GEMINI_API_KEY: Optional[str] = app_settings.gemini_api_key

# ─── Production Startup Validator ───────────────────────────────────────────
if app_settings.environment.lower() == "production":
    if not os.environ.get("JWT_SECRET"):
        raise RuntimeError("FATAL: JWT_SECRET environment variable is missing, but ENVIRONMENT is set to production!")
