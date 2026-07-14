import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

# Global State
datasets = {}
database_engine = None
db_flavor = None
current_source_type = "file"  # "file" or "sql"

settings = {
    "model": "qwen2.5:7b",
    "explain_mode": True,
    "debug_mode": False,
    "fast_mode": False
}

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
