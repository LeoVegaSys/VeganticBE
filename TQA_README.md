# Traffic QA — text-to-SQL + summarization service

Dynamic retrieval over the telecom traffic DuckDB DB. Plain-English question ->
DuckDB SQL (grounded in a business-facts block) -> result -> short summary.
Built for a UI: returns structured JSON and ships an HTTP endpoint with CORS.

## Setup
    export TRAFFIC_DB=/spindlepart/traffic.db
    # Ollama must be serving your model (default rafw007/qwen35-claude-coder:9b)
    # faster option: export QA_MODEL=qwen2.5-coder:7b

## CLI
    python traffic_qa.py "top 10 nodes by peak utilization"
    python traffic_qa.py --json "busiest LinkType by inbound traffic"
    python traffic_qa.py --no-summary "how many interfaces per LinkType"
    python traffic_qa.py            # interactive

## HTTP (for the frontend)
    python traffic_qa.py --serve --port 8000
    # POST /ask  body: {"question":"...", "summarize":true}
    # returns: {question, intent, sql, columns, rows, row_count, summary, error}

## Frontend call example
    fetch("http://HOST:8000/ask", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({question:"top 5 congested interfaces"})
    }).then(r=>r.json())

## Env vars
    TRAFFIC_DB    path to the DuckDB file (default /spindlepart/traffic.db)
    QA_MODEL      SQL-gen model (default rafw007/qwen35-claude-coder:9b)
    QA_SUM_MODEL  summary model (default = QA_MODEL)
    QA_TIMEOUT    per-call timeout seconds (default 120)
    QA_ROW_LIMIT  max rows returned (default 500)

## Tuning the brain
All correctness comes from BUSINESS_FACTS at the top of traffic_qa.py.
Edit that block when columns or rules change — it is what stops the model
summing rates over time, mis-quoting columns, or botching utilization.