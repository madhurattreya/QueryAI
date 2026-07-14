import os
import re

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

def prune_schema_for_query(schema_desc: str, question: str) -> str:
    """
    Prunes large schemas to only keep columns that are relevant to the user query terms or are IDs.
    """
    if not schema_desc:
        return ""
        
    lines = schema_desc.strip().split("\n")
    # If the schema is small, keep it as is
    if len(lines) < 25:
        return schema_desc
        
    q_words = set(re.findall(r"\b\w+\b", question.lower()))
    pruned_lines = []
    
    for line in lines:
        # Always keep structural header lines
        if line.startswith("Table:") or line.startswith("Dataset:") or "Columns and Types:" in line or "First 5 sample rows:" in line:
            pruned_lines.append(line)
            continue
            
        # Match keywords, column names, or ID columns
        matched = False
        for word in q_words:
            if len(word) > 2 and word in line.lower():
                matched = True
                break
                
        # Always keep primary keys and ID columns
        if not matched and any(x in line.lower() for x in ["id", "key", "pk", "fk"]):
            matched = True
            
        # Limit sample rows size if we are inside a sample block
        if matched or line.startswith(" ") or line.startswith("\t"):
            pruned_lines.append(line)
            
    return "\n".join(pruned_lines)

def build_prompt(template_name: str, **kwargs) -> str:
    """
    Compiles a structured prompt using the loaded template and keyword arguments,
    pruning schema description for token optimization.
    """
    template = get_template(template_name)
    if not template:
        return kwargs.get("question", "")
        
    # Ensure system context is prepended
    system_ctx = ""
    if template_name != "system" and template_name != "summary":
        system_ctx = get_template("system")
        if system_ctx:
            system_ctx += "\n"
            
    # Process optional parameters with defaults
    schema = kwargs.get("schema_desc", "")
    profile = kwargs.get("profile_desc", "")
    question = kwargs.get("question", "")
    
    # Apply Retrieval-Augmented Schema (RAS) column pruning
    if schema and question:
        kwargs["schema_desc"] = prune_schema_for_query(schema, question)
    if profile and question:
        kwargs["profile_desc"] = prune_schema_for_query(profile, question)
        
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
