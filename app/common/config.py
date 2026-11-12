import os

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "lumen-poc-srao26")

EMBED_MODEL = os.environ.get("EMBED_MODEL", "gemini-embedding-001")
EMBED_LOCATION = os.environ.get("EMBED_LOCATION", "us-east1")
EMBED_DIMS = int(os.environ.get("EMBED_DIMS", "768"))

LLM_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
LLM_LOCATION = os.environ.get("GEMINI_LOCATION", "global")
GATE_MODEL = os.environ.get("GATE_MODEL", LLM_MODEL)

PROJECT_NUMBER = os.environ.get("PROJECT_NUMBER", "807627578504")
AGENT_REGION = os.environ.get("AGENT_REGION", "us-east1")

LIVE_PER_VISITOR_DAY = int(os.environ.get("LIVE_PER_VISITOR_DAY", "2"))
LIVE_PER_DAY = int(os.environ.get("LIVE_PER_DAY", "6"))
LIVE_PER_MONTH = int(os.environ.get("LIVE_PER_MONTH", "60"))
VISITOR_SALT = os.environ.get("VISITOR_SALT", "local-development-salt")
