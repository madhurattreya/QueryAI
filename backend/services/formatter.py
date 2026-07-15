import sys
import pandas as pd
import backend.config as config
from backend.services.llm import call_llm

MAX_ROWS = 20

# CLI Flag Checkers (fallback for CLI runner)
explain_mode = "--explain" in sys.argv
fast_mode = "--fast" in sys.argv
debug_mode = "--debug" in sys.argv

# Sync status
if not explain_mode and not fast_mode and not debug_mode:
    explain_mode = config.settings.get("explain_mode", True)
    fast_mode = config.settings.get("fast_mode", False)
    debug_mode = config.settings.get("debug_mode", False)
technical_mode = config.settings.get("technical_mode", False)
explain_level = config.settings.get("explain_level", "Normal")

def print_structured_output(question: str, code: str, result, explanation: str, elapsed_time: float, rows_count: int, model_name: str, prompt: str = None):
    """
    Renders execution outputs in the beautiful ASCII layout depending on active flags.
    """
    if debug_mode:
        print("\n============================================================")
        print("                  DEBUG METADATA LOGS")
        print("============================================================\n")
        if prompt:
            print("[GENERATED PROMPT]")
            print(f"{prompt}\n")
        print("[GENERATED QUERY/CODE]")
        print(f"{code}\n")
        print(f"Time Taken : {elapsed_time:.2f} sec")
        print(f"Rows Count : {rows_count}")
        print(f"Model Name : {model_name}")
        print("============================================================\n")

    print("\n============================================================")
    print("                   AI DATA ANALYST")
    print("============================================================\n")
    print("[QUESTION]")
    print(f"{question}\n")

    if not fast_mode:
        print("[GENERATED QUERY]")
        print(f"{code}\n")

    print("[RESULT]")
    if isinstance(result, pd.DataFrame):
        if result.empty:
            print("No matching data found.")
        else:
            if len(result) > MAX_ROWS:
                print(result.head(MAX_ROWS).to_string(index=False))
                print(f"\n[INFO] Showing first {MAX_ROWS} of {len(result)} rows.")
            else:
                print(result.to_string(index=False))
    elif isinstance(result, pd.Series):
        if result.empty:
            print("No matching data found.")
        else:
            if len(result) > MAX_ROWS:
                print(result.head(MAX_ROWS).to_string())
                print(f"\n[INFO] Showing first {MAX_ROWS} of {len(result)} rows.")
            else:
                print(result.to_string())
    else:
        print(result)
    print()

    if (explain_mode or debug_mode) and explanation:
        print("[INTERPRETATION]")
        print(f"{explanation}\n")

    print("============================================================")
    print(f"Time Taken : {elapsed_time:.2f} sec")
    print(f"Model      : {model_name}")
    print(f"Rows       : {rows_count}")
    print("============================================================\n")

def print_error_output(question: str, error_msg: str, elapsed_time: float, model_name: str, rows_count: int = 0):
    print("\n============================================================")
    print("                   AI DATA ANALYST")
    print("============================================================\n")
    print("[QUESTION]")
    print(f"{question}\n")
    print(f"[ERROR] Error: {error_msg}\n")
    print("============================================================")
    print(f"Time Taken : {elapsed_time:.2f} sec")
    print(f"Model      : {model_name}")
    print(f"Rows       : {rows_count}")
    print("============================================================\n")

def show_followup_suggestions(question: str, schema_info: str, result_summary: str):
    if fast_mode:
        return

    prompt = f"""
You are a Data Analyst Copilot.
Based on the schema description, the user's question, and the summary of the result:

Schema:
{schema_info}

User Question: {question}
Result: {result_summary}

Suggest 3 logical, interesting, and useful follow-up questions that the user can ask next to explore this data deeper.

Rules:
1. Return ONLY the 3 suggestions as bullet points (e.g. "• Suggestion 1").
2. Do not write introductory text, explanations, or conclusion.
3. Keep each suggestion short and clear (one sentence max).
"""

    try:
        suggestions = call_llm(prompt).strip()
        print("[SUGGESTIONS FOR NEXT STEPS]")
        print(suggestions)
        print("============================================================\n")
    except Exception:
        pass
