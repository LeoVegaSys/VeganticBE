import json


def get_summarize_prompt(state: dict) -> str:
    preview = json.dumps(state["rows"][:40], default=str)

    return f"""You are a telecom NOC analyst. Answer the question from the result ONLY.
Respond in ENGLISH, 2-4 sentences. Name the key entities with their numbers.
Convert Kbps to Mbps/Gbps when large. Flag utilization > 100 as a likely stale-BW issue.
Do not restate the whole table or explain the SQL.

QUESTION: {state["question"]}
COLUMNS: {state["columns"]}
ROWS: {preview}
"""


def fallback_summarize(rows: list) -> str:
    if not rows: 
        return "No matching rows."
    return f"Returned {len(rows)} row(s). Top row: {rows[0]}"