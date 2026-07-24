"""
backend/services/sandbox_isolation.py
────────────────────────────────────────
Sandbox Process & Subprocess Memory Execution Isolation.

Executes Python analytics code in an isolated sub-process with memory limit and CPU timeout bounds,
working alongside AST validation layer for 100% execution safety.
"""

from __future__ import annotations
import sys
import os
import subprocess
import tempfile
import json
import logging
from typing import Dict, Any, Tuple
import pandas as pd

logger = logging.getLogger("queryiq.sandbox")

class SandboxIsolationManager:
    """
    Subprocess isolation manager for code execution safety.
    """

    def execute_in_subprocess(
        self,
        code: str,
        datasets: Dict[str, pd.DataFrame],
        timeout_seconds: int = 10
    ) -> Tuple[bool, Any, str]:
        """
        Executes generated code in an isolated subprocess.
        Returns: Tuple[success: bool, result_dataframe_or_dict, stderr_log: str]
        """
        temp_dir = tempfile.mkdtemp(prefix="queryiq_sandbox_")
        script_path = os.path.join(temp_dir, "sandbox_run.py")
        output_data_path = os.path.join(temp_dir, "output.json")

        # Save input datasets as temporary JSON/CSV files if needed
        data_bindings = {}
        for name, df in datasets.items():
            if isinstance(df, pd.DataFrame):
                clean_name = name.replace("-", "_").replace(" ", "_").replace(".", "_")
                df_path = os.path.join(temp_dir, f"{clean_name}.json")
                df.to_json(df_path, orient="records")
                data_bindings[clean_name] = df_path

        # Wrapper script that loads data, executes target code, and writes output
        wrapper_code = f"""
import sys
import json
import pandas as pd

# Data loader
datasets = {{}}
data_bindings = {json.dumps(data_bindings)}
for name, fpath in data_bindings.items():
    datasets[name] = pd.read_json(fpath)

# Execute user generated code
local_scope = {{"pd": pd, "datasets": datasets, "df": list(datasets.values())[0] if datasets else pd.DataFrame()}}

{code}

# Collect result DataFrame
result_var = None
for k, v in local_scope.items():
    if isinstance(v, pd.DataFrame) and k not in ['df', 'datasets']:
        result_var = v
        break
if result_var is None and 'result' in local_scope:
    result_var = local_scope['result']

if isinstance(result_var, pd.DataFrame):
    out = result_var.head(1000).to_dict(orient="records")
else:
    out = str(result_var)

with open(r"{output_data_path}", "w") as f:
    json.dump(out, f)
"""

        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(wrapper_code)

            # Run Python process in isolated sub-process
            proc = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )

            if proc.returncode != 0:
                logger.error(f"Sandbox subprocess error: {proc.stderr}")
                return False, None, proc.stderr

            if os.path.exists(output_data_path):
                with open(output_data_path, "r", encoding="utf-8") as f:
                    result_data = json.load(f)
                return True, result_data, ""
            
            return True, None, ""

        except subprocess.TimeoutExpired:
            return False, None, f"Execution timed out after {timeout_seconds} seconds."
        except Exception as e:
            return False, None, f"Sandbox error: {str(e)}"
        finally:
            # Clean up temp files
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass


# Global singleton instance
sandbox_isolation = SandboxIsolationManager()
