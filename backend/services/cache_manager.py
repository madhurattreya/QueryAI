"""
backend/services/cache_manager.py
──────────────────────────────────
Thread-safe, multi-namespace cache manager with TTL and LRU eviction policies.

Supported namespaces:
  - schema (TTL 3600s, cleared on dataset upload)
  - query_results (TTL 1800s, max 500 entries, LRU eviction)
  - prompts (Infinite TTL, cached until manual template change)
  - conversation (TTL 900s, max 1000 entries, LRU eviction)
  - kpi (TTL 1800s, cleared on dataset change)
"""
from __future__ import annotations
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import backend.config as config


class CacheEntry:
    """A single cache entry holding the value, expiration time, and last access time."""

    def __init__(self, value: Any, ttl_seconds: Optional[int] = None):
        self.value = value
        self.created_at = time.time()
        self.expires_at = (self.created_at + ttl_seconds) if ttl_seconds is not None else None
        self.last_accessed = self.created_at

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def touch(self) -> None:
        self.last_accessed = time.time()


class NamespaceCache:
    """Thread-safe cache container for a single namespace with LRU eviction."""

    def __init__(self, name: str, default_ttl: Optional[int], max_entries: Optional[int] = None):
        self.name = name
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._lock = threading.RLock()
        self._store: Dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.is_expired:
                del self._store[key]
                return None
            entry.touch()
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        with self._lock:
            # Enforce LRU eviction if full
            if self.max_entries and len(self._store) >= self.max_entries:
                self._evict_lru()

            ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
            self._store[key] = CacheEntry(value, ttl)

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def cleanup_expired(self) -> int:
        """Removes expired entries. Returns count of removed items."""
        with self._lock:
            now = time.time()
            expired_keys = [k for k, e in self._store.items() if e.is_expired]
            for k in expired_keys:
                del self._store[k]
            return len(expired_keys)

    def size(self) -> int:
        with self._lock:
            self.cleanup_expired()
            return len(self._store)

    def _evict_lru(self) -> None:
        """Evicts the least recently accessed (or expired) entry."""
        now = time.time()
        # Find any expired first
        expired_keys = [k for k, e in self._store.items() if e.is_expired]
        if expired_keys:
            for k in expired_keys:
                del self._store[k]
            return

        # Otherwise find LRU
        lru_key = None
        lru_time = now
        for k, entry in self._store.items():
            if entry.last_accessed < lru_time:
                lru_time = entry.last_accessed
                lru_key = k
        if lru_key:
            del self._store[lru_key]


class CacheManager:
    """
    Singleton cache coordinator managing all namespaces.
    Ensures thread-safe configurations.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(CacheManager, cls).__new__(cls, *args, **kwargs)
                cls._instance._initialize_namespaces()
            return cls._instance

    def _initialize_namespaces(self) -> None:
        # Pull configurations from global app settings
        ttl_query = config.app_settings.query_cache_ttl_seconds
        ttl_schema = config.app_settings.schema_cache_ttl_seconds
        ttl_conv = config.app_settings.conversation_cache_ttl_seconds
        ttl_kpi = config.app_settings.kpi_cache_ttl_seconds
        max_query = config.app_settings.query_cache_max_entries

        self.namespaces: Dict[str, NamespaceCache] = {
            "schema": NamespaceCache("schema", default_ttl=ttl_schema),
            "query_results": NamespaceCache("query_results", default_ttl=ttl_query, max_entries=max_query),
            "prompts": NamespaceCache("prompts", default_ttl=None),  # Infinite
            "conversation": NamespaceCache("conversation", default_ttl=ttl_conv, max_entries=1000),
            "kpi": NamespaceCache("kpi", default_ttl=ttl_kpi),
        }

    # ── Namespace accessors ────────────────────────────────────────────────────

    def get_namespace(self, name: str) -> NamespaceCache:
        return self.namespaces[name]

    def get(self, namespace: str, key: str) -> Optional[Any]:
        return self.namespaces[namespace].get(key)

    def set(self, namespace: str, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        self.namespaces[namespace].set(key, value, ttl_seconds)

    def delete(self, namespace: str, key: str) -> bool:
        return self.namespaces[namespace].delete(key)

    def clear_namespace(self, namespace: str) -> None:
        self.namespaces[namespace].clear()

    def clear_all(self) -> None:
        for ns in self.namespaces.values():
            ns.clear()

    def run_garbage_collection(self) -> Dict[str, int]:
        """Cleans up expired keys across all namespaces. Returns metrics."""
        return {name: ns.cleanup_expired() for name, ns in self.namespaces.items()}
