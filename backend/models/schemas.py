from pydantic import BaseModel

class SQLConnectionRequest(BaseModel):
    db_type: str # sqlite, mysql, postgresql
    sqlite_path: str | None = None
    host: str = "localhost"
    port: str | None = None
    db_name: str = ""
    username: str = ""
    password: str = ""

class SettingsRequest(BaseModel):
    model: str
    explain_mode: bool
    debug_mode: bool
    fast_mode: bool

class QueryRequest(BaseModel):
    question: str
    conversation_id: str | None = None

class SwitchSourceRequest(BaseModel):
    source_type: str
