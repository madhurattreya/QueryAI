"""
backend/services/engines/llm_engine.py
──────────────────────────────────────
LLM Query Engine.
Coordinates prompt compilation, LLM model calls,
and code execution within the safe sandbox, incorporating self-healing retry logic.
"""
from __future__ import annotations
import re
import time
import json
import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

import backend.config as config
from backend.models.execution_plan import ExecutionPlan
import backend.services.security as security
import backend.services.engine as engine
from backend.services.llm import LLMManager


class LLMEngine:
    """
    Core executor for LLM-driven query code generation and correction loops.
    """

    def __init__(self):
        self.llm_manager = LLMManager()

    def run_sandbox_code(self, code: str, timeout: int | None = None) -> Any:
        """
        Executes generated Python code inside the safe local sandbox.
        """
        if timeout is None:
            timeout = config.app_settings.sandbox_timeout_seconds
        security.validate_code(code)
        
        safe_builtins = {
            'len': len, 'str': str, 'int': int, 'float': float, 'sum': sum,
            'max': max, 'min': min, 'abs': abs, 'any': any, 'all': all,
            'zip': zip, 'enumerate': enumerate, 'range': range, 'list': list,
            'dict': dict, 'set': set, 'tuple': tuple, 'bool': bool, 'round': round
        }
        
        local_vars = {name: df_item for name, df_item in config.datasets.items()}
        if config.datasets:
            active_name = list(config.datasets.keys())[0]
            local_vars["df"] = config.datasets[active_name]
            local_vars.update(engine.build_safe_column_aliases(config.datasets[active_name]))
            
        local_vars["result"] = None
        local_vars["pd"] = pd
        if engine.HAS_PLOTLY:
            local_vars["go"] = engine.go
            local_vars["px"] = engine.px
            
        engine.run_query_with_timeout(code, {"__builtins__": safe_builtins}, local_vars, timeout=timeout)
        result = local_vars.get("result")
        if result is None:
            raise ValueError("The generated Python code did not assign a value to the 'result' variable.")
        return result
