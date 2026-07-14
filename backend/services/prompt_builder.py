import os

PROMPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts"))

_templates_cache = {}

def get_template(name: str) -> str:
    """
    Loads and caches the prompt template markdown file from disk.
    """
    global _templates_cache
    if name in _templates_cache:
        return _templates_cache[name]
        
    path = os.path.join(PROMPTS_DIR, f"{name}.md")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                _templates_cache[name] = content
                return content
        except Exception:
            pass
    return ""

def build_prompt(template_name: str, **kwargs) -> str:
    """
    Compiles a structured prompt using the loaded template and keyword arguments.
    """
    template = get_template(template_name)
    if not template:
        # Fallback in case template file is missing
        return kwargs.get("question", "")
        
    # Ensure system context is prepended if not already present
    system_ctx = ""
    if template_name != "system" and template_name != "summary":
        system_ctx = get_template("system")
        if system_ctx:
            system_ctx += "\n"
            
    # Process optional parameters with defaults
    kwargs.setdefault("schema_desc", "")
    kwargs.setdefault("profile_desc", "")
    kwargs.setdefault("summary_block", "")
    kwargs.setdefault("history_block", "")
    kwargs.setdefault("plan_block", "")
    kwargs.setdefault("db_flavor", "SQL")
    kwargs.setdefault("question", "")
    kwargs.setdefault("result_str", "")
    kwargs.setdefault("error_msg", "")
    kwargs.setdefault("failed_code", "")
    
    formatted_prompt = template.format(**kwargs)
    return system_ctx + formatted_prompt
