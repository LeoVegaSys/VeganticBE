import os
import json
from dotenv import load_dotenv
from models.llm_manager import LLMManager_REST

load_dotenv()

def summarize(state: dict):
    preview = json.dumps(state["rows"][:40], default=str)
    prompt = f"""You are a telecom NOC analyst. Answer the question from the result ONLY.
Respond in ENGLISH, 2-4 sentences. Name the key entities with their numbers.
Convert Kbps to Mbps/Gbps when large. Flag utilization > 100 as a likely stale-BW issue.
Do not restate the whole table or explain the SQL.

QUESTION: {state["question"]}
COLUMNS: {state["cols"]}
ROWS: {preview}
"""
    return LLMManager_REST().call(
        prompt=prompt, 
        model=os.environ.get("QA_SUM_MODEL"), 
        temperature=0.2
        ).strip()

def fallback_summarize(state: dict):
    rows=state["rows"]
    if not rows: return "No matching rows."
    return f"Returned {len(rows)} row(s). Top row: {rows[0]}"