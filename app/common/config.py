import os

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "lumen-poc-srao26")

EMBED_MODEL = os.environ.get("EMBED_MODEL", "gemini-embedding-001")
EMBED_LOCATION = os.environ.get("EMBED_LOCATION", "us-east1")
EMBED_DIMS = int(os.environ.get("EMBED_DIMS", "768"))

LLM_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
LLM_LOCATION = os.environ.get("GEMINI_LOCATION", "global")
GATE_MODEL = os.environ.get("GATE_MODEL", LLM_MODEL)
