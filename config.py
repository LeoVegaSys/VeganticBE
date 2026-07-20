from dotenv import load_dotenv
load_dotenv()

import os

OLLAMA_URL=os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_HOST=os.getenv("OLLAMA_HOST", "localhost")
OLLAMA_PORT=int(os.getenv("OLLAMA_PORT", 11434))

SQL_MODEL=os.getenv("QA_MODEL", "qwen2.5-coder:7b")
SUMMARY_MODEL=os.getenv("QA_SUM_MODEL", "llama3.2:3b")
QA_TIMEOUT=int(os.getenv("QA_TIMEOUT", 180))
QA_ROW_LIMIT=int(os.getenv("QA_ROW_LIMIT", 500))
OLLAMA_KEEP_ALIVE=os.getenv("OLLAMA_KEEP_ALIVE", "30m")

QA_MAX_REPAIRS=int(os.getenv("QA_MAX_REPAIRS", 1))

LOG_FILE=os.getenv("QA_LOG_FILE", "qa_log.jsonl")
FEEDBACK_LOG_FILE=os.getenv("QA_FEEDBACK_LOG_FILE", "qa_feedback.jsonl")

BUSINESS_FACTS=os.getenv("QA_BUSINESS_FACTS", "business_facts.md")

DIP_MIN_DROP=int(os.getenv("QA_DIP_MIN_DROP", 20))
DIP_HIGH_UTIL=int(os.getenv("QA_DIP_HIGH_UTIL", 80))

SERVER_HOST=os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT=int(os.getenv("SERVER_PORT", 8000))

MCP_DB_PATH=os.getenv("DB_PATH")
MCP_DB_TYPE=os.getenv("MCP_DB_TYPE", "mysql")
TRAFFIC_TABLE_NAME=os.getenv("TRAFFIC_TABLE_NAME", "traffic")
DB_ENDPOINT_URL = os.getenv("DB_ENDPOINT_URL")


CHART_INTENT_ALIASES = {"timeseries": "trend", "dip": "ranking"}