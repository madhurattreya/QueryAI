from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import backend.config as _config

class ExecutionContext(BaseModel):
    conversation_id: str
    dataset_id: str
    dataset_version: str
    engine: str = "general_chat"  # metadata, lookup, aggregation, filter, visualization, prediction, explanation, general_chat
    schema_desc: str = ""
    profile_desc: str = ""
    router_result: str = ""
    cached: bool = False
    history: List[Dict[str, Any]] = []
    model: str = Field(default_factory=lambda: _config.app_settings.default_model)
    temperature: float = 0.0
    prompt: str = ""
    question: str = ""
    execution_plan: Optional[str] = None
    chart_requested: bool = False
    code: Optional[str] = None
    raw_result: Any = None
    explanation: Optional[str] = None
    error: Optional[str] = None
    timings: Dict[str, float] = {}
    prompt_size: int = 0
    rows: int = 0
    complexity: str = "simple"  # simple, complex

    class Config:
        arbitrary_types_allowed = True
