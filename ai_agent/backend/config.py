import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load private environment variables from the project root.
load_dotenv(PROJECT_ROOT / ".env")

# AI provider configuration
AI_PRIMARY_PROVIDER = os.getenv("AI_PRIMARY_PROVIDER", "gemini")
AI_SECONDARY_PROVIDER = os.getenv("AI_SECONDARY_PROVIDER", "groq")
AI_LOCAL_PROVIDER = os.getenv("AI_LOCAL_PROVIDER", "ollama")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
)

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
)
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:3b"
)

# BigQuery configuration
BIGQUERY_PROJECT_ID = os.getenv(
    "BIGQUERY_PROJECT_ID",
    "winter-sensor-474220-u4"
)
BIGQUERY_DATASET = os.getenv(
    "BIGQUERY_DATASET",
    "datapulse_marts"
)

BIGQUERY_LOCATION = os.getenv(
    "BIGQUERY_LOCATION",
    "asia-south1"
)

BIGQUERY_QUERY_TIMEOUT_SECONDS = int(
    os.getenv("BIGQUERY_QUERY_TIMEOUT_SECONDS", "30")
)

BIGQUERY_MAX_BYTES_BILLED = int(
    os.getenv("BIGQUERY_MAX_BYTES_BILLED", "1000000000")
)