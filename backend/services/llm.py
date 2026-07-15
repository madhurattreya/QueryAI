"""
backend/services/llm.py
────────────────────────
LLM communication layer with:
  - Per-call timeout enforcement (LLM_TIMEOUT_SECONDS from .env)
  - Retry-once on timeout, then structured LLMTimeoutError
  - LLMCallMetrics dataclass attached to every call
  - Fallback chain across multiple models
"""
import os
import json
import urllib.request
import urllib.error
import time
import concurrent.futures
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import backend.config as config


# ─── Custom exception ─────────────────────────────────────────────────────────

class LLMTimeoutError(RuntimeError):
    """Raised when the LLM exceeds the configured timeout after retry."""
    pass


class LLMUnavailableError(RuntimeError):
    """Raised when all models in the fallback chain fail."""
    pass


# ─── Metrics dataclass ────────────────────────────────────────────────────────

@dataclass
class LLMCallMetrics:
    model_used: str = ""
    prompt_tokens: int = 0          # estimated: word-count / 0.75
    completion_tokens: int = 0      # estimated: word-count / 0.75
    generation_time_ms: float = 0.0
    retry_count: int = 0
    failure_reason: Optional[str] = None
    timed_out: bool = False


def _estimate_tokens(text: str) -> int:
    """Fast token estimate: ~0.75 words/token heuristic."""
    return max(1, int(len(text.split()) / 0.75))


# ─── LLM Manager ─────────────────────────────────────────────────────────────

class LLMManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LLMManager, cls).__new__(cls, *args, **kwargs)
            cls._instance.opener = urllib.request.build_opener()
        return cls._instance

    def call_model(self, model: str, prompt: str, temperature: float = 0.0) -> str:
        """
        Sends query directly to the specified model.
        Respects LLM_TIMEOUT_SECONDS. Does NOT retry internally.
        """
        timeout = config.app_settings.llm_timeout_seconds

        if "gemini" in model.lower():
            api_key = config.GEMINI_API_KEY
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not set in .env. Please configure it to use Gemini."
                )

            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-1.5-flash:generateContent?key={api_key}"
            )
            data = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature},
            }
            req_data = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"},
            )
            with self.opener.open(req, timeout=timeout) as res:
                response = json.loads(res.read().decode("utf-8"))
                return response["candidates"][0]["content"]["parts"][0]["text"]

        else:
            # Local Ollama — run in thread so we can enforce timeout
            from ollama import chat

            def _ollama_call():
                return chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": temperature},
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_ollama_call)
                try:
                    response = future.result(timeout=timeout)
                    return response["message"]["content"]
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    raise LLMTimeoutError(
                        f"Ollama model '{model}' timed out after {timeout}s."
                    )

    def call_llm_with_fallback(
        self,
        prompt: str,
        primary_model: str,
        temperature: float = 0.0,
        fallback_list: Optional[List[str]] = None,
    ) -> Tuple[str, str, LLMCallMetrics]:
        """
        Runs LLM call with a fallback chain and retry-once-on-timeout policy.

        Returns:
            (response_text, final_model_used, LLMCallMetrics)
        """
        metrics = LLMCallMetrics()
        max_retries = config.app_settings.llm_max_retries

        if fallback_list is None:
            fallback_list = [primary_model]
            # Local Ollama fallback chain: use known-available models on this machine
            local_fallbacks = ["qwen2.5:3b", "qwen2.5:7b", "gemma4:latest", "gemma4"]
            if "gemini" in primary_model.lower():
                fallback_list.extend(local_fallbacks)
            else:
                # Add remaining local models not already in the chain
                fallback_list.extend([m for m in local_fallbacks if m != primary_model])

        # Deduplicate while preserving order
        seen: set = set()
        clean_fallback = [m for m in fallback_list if not (m in seen or seen.add(m))]

        metrics.prompt_tokens = _estimate_tokens(prompt)
        last_error: Optional[Exception] = None

        for model in clean_fallback:
            attempt = 0
            while attempt <= max_retries:
                t_start = time.time()
                try:
                    result = self.call_model(model, prompt, temperature)
                    elapsed_ms = (time.time() - t_start) * 1000

                    metrics.model_used = model
                    metrics.generation_time_ms = round(elapsed_ms, 2)
                    metrics.completion_tokens = _estimate_tokens(result)
                    metrics.retry_count += attempt

                    return result, model, metrics

                except LLMTimeoutError as timeout_err:
                    elapsed_ms = (time.time() - t_start) * 1000
                    metrics.timed_out = True
                    metrics.retry_count += 1
                    print(
                        f"[LLM TIMEOUT] Model '{model}' timed out (attempt {attempt + 1}) "
                        f"after {elapsed_ms:.0f}ms."
                    )
                    last_error = timeout_err
                    attempt += 1
                    if attempt > max_retries:
                        # Retries on this model exhausted — try the next fallback model
                        print(
                            f"[LLM TIMEOUT] '{model}' exhausted all {max_retries + 1} attempt(s). "
                            f"Trying next fallback model..."
                        )
                        break  # Move to next model in fallback chain

                except Exception as e:
                    elapsed_ms = (time.time() - t_start) * 1000
                    print(
                        f"[LLM FALLBACK] Model '{model}' failed (attempt {attempt + 1}): "
                        f"{str(e)}. Trying next model..."
                    )
                    metrics.failure_reason = str(e)
                    last_error = e
                    break  # Move to next fallback model

            time.sleep(0.15)  # Brief backoff before trying next model

        metrics.failure_reason = str(last_error)
        raise LLMUnavailableError(
            f"All models in the fallback chain failed. Last error: {last_error}"
        )


# ─── Legacy entry point (backward compatible) ─────────────────────────────────

def call_llm(prompt: str) -> str:
    """
    Backward-compatible wrapper used by formatter.py and other legacy callers.
    Returns only the response text.
    """
    model = config.settings.get("model", config.app_settings.default_model)
    manager = LLMManager()
    res, _, _ = manager.call_llm_with_fallback(prompt, model)
    return res
