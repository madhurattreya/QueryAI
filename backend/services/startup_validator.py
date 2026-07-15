"""
backend/services/startup_validator.py
──────────────────────────────────────
Validates the environment at application startup.
All checks are non-fatal: the app continues even if some checks fail.
Results are printed to stdout with [STARTUP OK] / [STARTUP WARN] prefix.
"""
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import List
import backend.config as config


@dataclass
class StartupCheckResult:
    name: str
    status: str        # "ok" | "warn" | "error"
    message: str


class StartupValidator:
    """
    Runs all startup health checks.
    Call run_all_checks() once during lifespan startup.
    """

    def run_all_checks(self) -> List[StartupCheckResult]:
        checks = [
            self.check_prompt_files(),
            self.check_ollama_reachable(),
            self.check_model_available(),
            self.check_cache_dir(),
            self.check_dataset_registry(),
        ]
        self._print_results(checks)
        return checks

    # ── Individual Checks ─────────────────────────────────────────────────────

    def check_prompt_files(self) -> StartupCheckResult:
        """Verify all required prompt template markdown files exist."""
        prompts_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "prompts")
        )
        required = ["pandas.md", "sql.md", "system.md", "explanation.md", "correction.md"]
        missing = [f for f in required if not os.path.exists(os.path.join(prompts_dir, f))]

        if not missing:
            return StartupCheckResult("Prompt Files", "ok", f"All {len(required)} templates present.")
        else:
            return StartupCheckResult(
                "Prompt Files", "warn",
                f"Missing prompt files: {missing}. Some query paths may fail."
            )

    def check_ollama_reachable(self) -> StartupCheckResult:
        """Ping the Ollama service to confirm it is running."""
        base_url = config.app_settings.ollama_base_url
        url = f"{base_url}/api/tags"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as res:
                if res.status == 200:
                    return StartupCheckResult("Ollama Service", "ok", f"Reachable at {base_url}")
        except Exception as e:
            return StartupCheckResult(
                "Ollama Service", "warn",
                f"Cannot reach Ollama at {base_url}: {e}. Local model queries will fail."
            )
        return StartupCheckResult("Ollama Service", "warn", f"Unexpected response from {base_url}.")

    def check_model_available(self) -> StartupCheckResult:
        """Check if the configured default model is pulled in Ollama."""
        import json
        base_url = config.app_settings.ollama_base_url
        model_name = config.app_settings.default_model
        url = f"{base_url}/api/tags"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as res:
                data = json.loads(res.read().decode("utf-8"))
                available_models = [m.get("name", "") for m in data.get("models", [])]
                # Match by prefix (e.g. "qwen2.5:7b" matches "qwen2.5:7b-instruct-q4_0")
                matched = [m for m in available_models if m.startswith(model_name.split(":")[0])]
                if matched:
                    return StartupCheckResult(
                        "Default Model", "ok",
                        f"Model '{model_name}' is available (found: {matched[0]})."
                    )
                else:
                    return StartupCheckResult(
                        "Default Model", "warn",
                        f"Model '{model_name}' not found in Ollama. "
                        f"Available: {available_models[:5]}. Run: ollama pull {model_name}"
                    )
        except Exception as e:
            return StartupCheckResult(
                "Default Model", "warn",
                f"Could not check model availability: {e}"
            )

    def check_cache_dir(self) -> StartupCheckResult:
        """Verify the data directory is writable for cache files."""
        from backend.services.loader import DATA_DIR
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            test_file = os.path.join(DATA_DIR, ".startup_write_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return StartupCheckResult("Cache Directory", "ok", f"Writable: {DATA_DIR}")
        except Exception as e:
            return StartupCheckResult(
                "Cache Directory", "warn",
                f"Cache directory not writable ({DATA_DIR}): {e}. Caching will be disabled."
            )

    def check_dataset_registry(self) -> StartupCheckResult:
        """Check if any dataset is loaded in memory."""
        if config.datasets and len(config.datasets) > 0:
            names = list(config.datasets.keys())
            return StartupCheckResult(
                "Dataset Registry", "ok",
                f"{len(names)} dataset(s) loaded: {names[:3]}"
            )
        else:
            return StartupCheckResult(
                "Dataset Registry", "warn",
                "No datasets loaded yet. Upload or connect a data source to begin querying."
            )

    # ── Printer ───────────────────────────────────────────────────────────────

    def _print_results(self, results: List[StartupCheckResult]) -> None:
        print("\n" + "=" * 60)
        print("  QueryIQ v{} — Startup Validation".format(
            config.app_settings.app_version
        ))
        print("=" * 60)
        for r in results:
            prefix = "[STARTUP OK  ]" if r.status == "ok" else "[STARTUP WARN]"
            print(f"  {prefix} {r.name}: {r.message}")
        print("=" * 60 + "\n")


# ─── Health status cache (30-second TTL for /api/health) ─────────────────────

_health_cache: dict = {}
_health_cache_ts: float = 0.0
_HEALTH_CACHE_TTL = 30.0


def get_system_health() -> dict:
    """
    Returns a live health snapshot of all subsystems.
    Cached for 30 seconds to avoid hammering Ollama on every /api/health poll.
    """
    global _health_cache, _health_cache_ts

    now = time.time()
    if _health_cache and (now - _health_cache_ts) < _HEALTH_CACHE_TTL:
        return _health_cache

    validator = StartupValidator()
    results = {r.name: r for r in validator.run_all_checks()}

    # Dataset
    ds_result = results.get("Dataset Registry")
    dataset_status = "loaded" if ds_result and ds_result.status == "ok" else "not_loaded"
    dataset_names = list(config.datasets.keys()) if config.datasets else []

    # LLM
    llm_result = results.get("Ollama Service")
    llm_status = "connected" if llm_result and llm_result.status == "ok" else "unreachable"
    model_result = results.get("Default Model")
    model_available = model_result.status == "ok" if model_result else False

    # Cache
    cache_result = results.get("Cache Directory")
    cache_status = "ok" if cache_result and cache_result.status == "ok" else "error"

    # Prompt files
    prompt_result = results.get("Prompt Files")
    prompt_status = "ok" if prompt_result and prompt_result.status == "ok" else "warn"

    # Uptime (approximate: tracked via import time)
    uptime_secs = round(now - _APP_START_TIME, 1)

    health = {
        "backend": "ok",
        "version": config.app_settings.app_version,
        "uptime_seconds": uptime_secs,
        "dataset": dataset_status,
        "dataset_count": len(dataset_names),
        "dataset_names": dataset_names[:5],
        "llm": llm_status,
        "model": config.app_settings.default_model,
        "model_available": model_available,
        "cache": cache_status,
        "prompt_files": prompt_status,
    }

    _health_cache = health
    _health_cache_ts = now
    return health


_APP_START_TIME = time.time()
