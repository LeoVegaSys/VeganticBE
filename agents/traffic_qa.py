#!/usr/bin/env python3
"""
Traffic QA — dynamic text-to-SQL + summarization over the telecom traffic DB.
=============================================================================
Schema-aware retrieval service for a UI. Give it a plain-English question;
it generates DuckDB SQL grounded in a business-facts block, runs it, and
returns structured JSON (sql + columns + rows + summary) the frontend can render.

Usage (CLI):
    python traffic_qa.py "top 10 nodes by peak utilization"
    python traffic_qa.py --json "busiest LinkType by inbound traffic"
    python traffic_qa.py --no-summary "how many interfaces per LinkType"

Usage (HTTP for a frontend):
    python traffic_qa.py --serve --port 8000
    # POST http://host:8000/ask   body: {"question": "...", "summarize": true}

Library:
    from traffic_qa import answer
    result = answer("top 5 congested interfaces")   # -> dict
"""
import os, re, sys, json, time, uuid, argparse, requests, duckdb

OLLAMA_URL   = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
SQL_MODEL    = os.environ.get("QA_MODEL", "qwen2.5-coder:7b")
SUM_MODEL    = os.environ.get("QA_SUM_MODEL", "llama3.2:3b")
LLM_TIMEOUT  = int(os.environ.get("QA_TIMEOUT", "180"))
DB_PATH      = os.environ.get("TRAFFIC_DB", "/spindlepart/traffic.db")
ROW_LIMIT    = int(os.environ.get("QA_ROW_LIMIT", "500"))
KEEP_ALIVE   = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
MAX_REPAIRS  = int(os.environ.get("QA_MAX_REPAIRS", "1"))   # keep at 1 for speed
LOG_FILE     = os.environ.get("QA_LOG_FILE", "/spindlepart/Traffic_QA/qa_log.jsonl")
FEEDBACK_LOG_FILE = os.environ.get("QA_FEEDBACK_LOG_FILE", "/spindlepart/Traffic_QA/qa_feedback.jsonl")
BUSINESS_FACTS_PATH = os.environ.get("QA_BUSINESS_FACTS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "business_facts.md"))
TABLE        = "traffic"

# ---------------------------------------------------------------------------
# BUSINESS FACTS — the context that makes a small model answer correctly.
# Edit these if your column names or rules change.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# BUSINESS FACTS — the domain/business rules that make a small model answer
# correctly. Lives in business_facts.md (next to this script, or wherever
# QA_BUSINESS_FACTS points), not in code, so it can be edited/reviewed/
# swapped per dataset without touching the script itself.
# ---------------------------------------------------------------------------
_FALLBACK_BUSINESS_FACTS = """\
DOMAIN: (business_facts.md not found — running with no domain rules loaded.
Set QA_BUSINESS_FACTS or place business_facts.md next to traffic_qa.py.)
"""

def load_business_facts(path=BUSINESS_FACTS_PATH):
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        print(f"[warn] could not load business facts from {path}: {e} — using fallback")
        return _FALLBACK_BUSINESS_FACTS

BUSINESS_FACTS = load_business_facts()

# ---------------------------------------------------------------------------
def _con():
    return duckdb.connect(DB_PATH, read_only=True)

def schema_context(con):
    cols = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position", [TABLE]).fetchall()
    schema = ", ".join(f'"{c}" {t}' for c, t in cols)
    lts = [r[0] for r in con.execute(f'SELECT DISTINCT "LinkType" FROM {TABLE}').fetchall() if r[0]]
    try:
        mn, mx = con.execute(f'SELECT MIN("Time"), MAX("Time") FROM {TABLE}').fetchone()
        when = f"{mn} -> {mx}"
    except Exception:
        when = "n/a"
    return schema, lts, when

def call_llm(prompt, model, temperature=0.0):
    r = requests.post(OLLAMA_URL, json={"model": model, "prompt": prompt,
                      "stream": False, "temperature": temperature, "keep_alive": KEEP_ALIVE}, timeout=LLM_TIMEOUT)
    r.raise_for_status()
    return r.json()["response"]

def _clean_sql(s):
    return s.replace("```sql", "").replace("```", "").strip().rstrip(";").strip()

def intent_tag(q):
    ql = q.lower()
    if any(w in ql for w in ("how many", "count", "number of")): return "count"
    if any(w in ql for w in ("top", "highest", "lowest", "busiest", "rank", "most", "least")): return "ranking"
    if any(w in ql for w in ("util", "congest", "capacity")): return "utilization"
    if any(w in ql for w in ("average", "avg", "total", "sum", "per ")): return "aggregation"
    if any(w in ql for w in ("over time", "trend", "by time", "each hour", "timeline")): return "timeseries"
    return "lookup"

# Bridges Python's internal intent naming to whatever the frontend chart-selection
# logic currently expects, without renaming intent_tag()'s output everywhere else.
CHART_INTENT_ALIASES = {"timeseries": "trend", "dip": "ranking"}

def gen_sql(con, question):
    schema, lts, when = schema_context(con)
    prompt = f"""You are an expert telecom analyst writing DuckDB SQL.

{BUSINESS_FACTS}

LIVE SCHEMA of table `{TABLE}`:
{schema}

Valid "LinkType" values: {lts}
Data time range: {when}

Write ONE DuckDB SQL query that answers the question.
Return ONLY the SQL — no markdown, no comments, no explanation.

Question: {question}
"""
    return _clean_sql(call_llm(prompt, SQL_MODEL, 0.0))

def run_sql(con, sql):
    low = sql.lower().lstrip()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("Only read-only SELECT/WITH queries are allowed.")
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchmany(ROW_LIMIT)
    data = [{c: (str(v) if hasattr(v, "isoformat") else v) for c, v in zip(cols, r)} for r in rows]
    return cols, data

def repair_sql(con, question, bad_sql, err):
    schema, _, _ = schema_context(con)
    prompt = f"""Fix this DuckDB SQL. Return ONLY corrected SQL.

{BUSINESS_FACTS}

SCHEMA: {schema}
QUESTION: {question}
BROKEN SQL: {bad_sql}
ERROR: {err}

Corrected SQL:"""
    return _clean_sql(call_llm(prompt, SQL_MODEL, 0.0))

def _run_with_repair(con, question, sql):
    """Try sql, repair up to MAX_REPAIRS times on failure.
    Returns (final_sql, cols, rows, attempts_trace). Raises on final failure."""
    trace = []
    cur_sql = sql
    for attempt in range(MAX_REPAIRS + 1):
        t0 = time.time()
        try:
            cols, rows = run_sql(con, cur_sql)
            trace.append({"n": attempt, "sql": cur_sql, "ok": True,
                          "ms": round((time.time() - t0) * 1000)})
            return cur_sql, cols, rows, trace
        except Exception as e:
            trace.append({"n": attempt, "sql": cur_sql, "ok": False, "error": str(e),
                          "ms": round((time.time() - t0) * 1000)})
            if attempt == MAX_REPAIRS:
                raise
            t0 = time.time()
            cur_sql = repair_sql(con, question, cur_sql, str(e))
            trace[-1]["repair_ms"] = round((time.time() - t0) * 1000)

def summarize(question, sql, cols, rows):
    preview = json.dumps(rows[:40], default=str)
    prompt = f"""You are a telecom NOC analyst. Answer the question from the result ONLY.
Respond in ENGLISH, 2-4 sentences. Name the key entities with their numbers.
Convert Kbps to Mbps/Gbps when large. Flag utilization > 100 as a likely stale-BW issue.
Do not restate the whole table or explain the SQL.

QUESTION: {question}
COLUMNS: {cols}
ROWS: {preview}
"""
    return call_llm(prompt, SUM_MODEL, 0.2).strip()

def _fallback_summary(cols, rows):
    if not rows: return "No matching rows."
    return f"Returned {len(rows)} row(s). Top row: {rows[0]}"

# ---------------------------------------------------------------------------
# DIP DETECTION — deterministic, NO LLM in the math (per handoff doc Section 3).
# current   = each interface's LATEST sample.
# baseline  = AVG of that interface's EARLIER samples, excluding the latest,
#             so the dip sample never dilutes its own baseline.
# dip%      = (baseline - current) / baseline * 100.  >0 = dropped, <0 = surged.
# ---------------------------------------------------------------------------
DIP_KEYWORDS = ("dip", "dips", "dipped", "drop", "dropped", "surge", "spike",
                "sudden", "fell", "fall", "plunge", "plunged")
DIP_MIN_DROP = float(os.environ.get("QA_DIP_MIN_DROP", "20"))
DIP_HIGH_UTIL = float(os.environ.get("QA_DIP_HIGH_UTIL", "80"))

def is_dip_question(q):
    ql = q.lower()
    return any(w in ql for w in DIP_KEYWORDS)

def _extract_limit(q, default=10):
    ql = q.lower()
    m = re.search(r'\b(?:limit|top)\s*(\d+)\b', ql)
    return int(m.group(1)) if m else default

def _extract_linktype(q, valid_linktypes):
    ql = q.lower()
    if "all linktype" in ql or "across all" in ql:
        return None
    for lt in valid_linktypes:
        if lt and lt.lower() in ql:
            return lt
    return None

def _extract_pct(q, keyword_pattern, default):
    """Pull an explicit percentage threshold out of the question, e.g.
    'dip of at least 30%' -> 30.0, 'utilization above 90' -> 90.0.
    Falls back to `default` if the question doesn't specify one."""
    m = re.search(rf'{keyword_pattern}\D{{0,15}}?(\d+(?:\.\d+)?)\s*%?', q.lower())
    return float(m.group(1)) if m else default

def _extract_window_hours(q, default=1):
    """Pull a time window out of the question. Defaults to last 1 hour of
    the interface's OWN history (per handoff doc Section 3 default),
    measured from the dataset's own latest timestamp, not wall-clock now()."""
    ql = q.lower()
    m = re.search(r'last\s*(\d+)\s*hour', ql)
    if m: return int(m.group(1))
    m = re.search(r'last\s*(\d+)\s*day', ql)
    if m: return int(m.group(1)) * 24
    if 'today' in ql: return 24
    if 'this week' in ql: return 24 * 7
    return default

def dip_detect(con, question):
    """Find interfaces whose latest sample dropped sharply vs their own recent
    baseline (baseline = avg of earlier samples within the window, excluding
    the latest sample itself). If the question also mentions utilization/high,
    additionally require the CURRENT sample to be at/above the utilization
    threshold -- this answers "dip before high utilization" style questions:
    recently dipped AND currently running hot.
    All thresholds (drop %, utilization %, window hours) can be overridden by
    the question text; effective values used are returned in `params_used`
    so the caller/frontend can show exactly what filter was applied.
    Returns (sql, cols, rows, ms, params_used)."""
    _, lts, _ = schema_context(con)
    limit = _extract_limit(question, 10)
    linktype = _extract_linktype(question, lts)
    want_high_util = any(w in question.lower() for w in ("util", "congest", "high", "capacity"))

    min_drop = _extract_pct(question, r'(?:dip|drop|fell|fall)(?:ped)?\s*(?:of|by)?\s*(?:at least|>=)?', DIP_MIN_DROP)
    high_util = _extract_pct(question, r'(?:util(?:ization)?|congest\w*)\s*(?:of|is|at least|above|>=)?', DIP_HIGH_UTIL) \
        if want_high_util else None
    window_hours = _extract_window_hours(question, default=1)

    linktype_filter = 'AND "LinkType" = ?' if linktype else ""
    util_filter = ('AND GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)") '
                   '/ NULLIF(c."BW(Kb)", 0) * 100 >= ?') if want_high_util else ""

    # Window is measured from the DATASET's own latest sample, not wall-clock
    # now() -- this dataset is historical/fixed, not a live stream.
    sql = f'''WITH data_end AS (SELECT MAX("Time") AS t FROM traffic),
windowed AS (
    SELECT "Node Name", "Interface Name", "LinkType", "BW(Kb)", "Time",
           "In Traffic (Kbps)", "Out Traffic (Kbps)"
    FROM traffic, data_end
    WHERE "Time" >= data_end.t - INTERVAL '{window_hours} hours'
    {linktype_filter}
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY "Node Name","Interface Name" ORDER BY "Time" DESC
    ) AS rn
    FROM windowed
),
current AS (SELECT * FROM ranked WHERE rn = 1),
baseline AS (
    SELECT "Node Name", "Interface Name",
           AVG(GREATEST("In Traffic (Kbps)","Out Traffic (Kbps)")) AS baseline_val
    FROM ranked WHERE rn > 1
    GROUP BY "Node Name", "Interface Name"
)
SELECT
    c."Node Name" AS "Node Name",
    c."Interface Name" AS "Interface Name",
    c."LinkType" AS "LinkType",
    c."Time" AS "Latest Time",
    ROUND(GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)"), 2) AS "Current (Kbps)",
    ROUND(b.baseline_val, 2) AS "Baseline (Kbps)",
    ROUND((b.baseline_val - GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)"))
          / NULLIF(b.baseline_val, 0) * 100, 2) AS "Dip %",
    ROUND(GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)")
          / NULLIF(c."BW(Kb)", 0) * 100, 2) AS "Current Utilization %"
FROM current c
JOIN baseline b
  ON b."Node Name" = c."Node Name" AND b."Interface Name" = c."Interface Name"
WHERE b.baseline_val > 0
  AND (b.baseline_val - GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)"))
      / NULLIF(b.baseline_val, 0) * 100 >= ?
  {util_filter}
ORDER BY "Dip %" DESC
LIMIT ?'''

    params = []
    if linktype: params.append(linktype)
    params.append(min_drop)
    if want_high_util: params.append(high_util)
    params.append(limit)

    params_used = {"min_drop_pct": min_drop, "window_hours": window_hours,
                   "linktype": linktype or "ALL", "limit": limit}
    if want_high_util:
        params_used["high_util_pct"] = high_util

    t0 = time.time()
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchmany(ROW_LIMIT)
    data = [{c: (str(v) if hasattr(v, "isoformat") else v) for c, v in zip(cols, r)} for r in rows]
    ms = round((time.time() - t0) * 1000)
    return sql, cols, data, ms, params_used

def _log_request(question, intent, attempts, total_ms, error=None, request_id=None):
    """Append one JSON line per request. Never raises — logging must not break a request."""
    try:
        line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "request_id": request_id,
                "question": question, "intent": intent, "attempts": attempts,
                "total_ms": total_ms, "error": error}
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(line, default=str) + "\n")
    except Exception:
        pass

def _log_feedback(body):
    """Append one JSON line per feedback submission from the frontend.
    Expected body: {request_id, panel_id, rating: 'up'|'down', comment?}.
    request_id/panel_id are free-form strings -- validated loosely since the
    frontend is the source of truth for what panel/question they refer to.
    Returns True on success, False on invalid input. Never raises."""
    try:
        rating = (body.get("rating") or "").strip().lower()
        if rating not in ("up", "down"):
            return False
        line = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "request_id": body.get("request_id"),
            "panel_id": body.get("panel_id"),
            "question": body.get("question"),
            "rating": rating,
            "comment": (body.get("comment") or "").strip()[:2000],
            "user": body.get("user"),
        }
        with open(FEEDBACK_LOG_FILE, "a") as f:
            f.write(json.dumps(line, default=str) + "\n")
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
def answer(question, summarize_result=True):
    """Main entrypoint. Returns a UI-ready dict."""
    t_start = time.time()
    request_id = uuid.uuid4().hex[:12]
    intent = "dip" if is_dip_question(question) else intent_tag(question)
    out = {"request_id": request_id, "question": question, "intent": intent,
           "chart_intent": CHART_INTENT_ALIASES.get(intent, intent),
           "sql": None, "columns": [], "rows": [], "row_count": 0,
           "summary": None, "error": None}
    attempts_used = 0
    try:
        con = _con()
    except Exception as e:
        out["error"] = f"db connect failed: {e}"
        _log_request(question, intent, 0, round((time.time() - t_start) * 1000),
                     out["error"], request_id)
        return out

    if intent == "dip":
        # Deterministic path -- no SQL-gen LLM call, no repair loop needed.
        try:
            sql, cols, rows, _ms, params_used = dip_detect(con, question)
            out["sql"] = sql
            out["params_used"] = params_used
            out["columns"], out["rows"], out["row_count"] = cols, rows, len(rows)
            if not rows:
                extra = f" and current utilization >= {params_used['high_util_pct']:.0f}%" \
                        if "high_util_pct" in params_used else ""
                out["summary"] = (f"No interfaces found with a dip of at least "
                                   f"{params_used['min_drop_pct']:.0f}% vs their baseline "
                                   f"(last {params_used['window_hours']}h, linktype="
                                   f"{params_used['linktype']}){extra}.")
            elif summarize_result:
                try:
                    out["summary"] = summarize(question, sql, cols, rows)
                except Exception as e:
                    out["summary"] = _fallback_summary(cols, rows) + f" [llm summary unavailable: {e}]"
        except Exception as e:
            out["error"] = str(e)
        finally:
            con.close()
        _log_request(question, intent, 0, round((time.time() - t_start) * 1000),
                     out["error"], request_id)
        return out

    try:
        sql = gen_sql(con, question)
        out["sql"] = sql
        try:
            sql, cols, rows, trace = _run_with_repair(con, question, sql)
        except Exception:
            attempts_used = MAX_REPAIRS + 1
            raise
        out["sql"] = sql
        attempts_used = len(trace)
        out["columns"], out["rows"], out["row_count"] = cols, rows, len(rows)
        if summarize_result:
            try:
                out["summary"] = summarize(question, out["sql"], cols, rows)
            except Exception as e:
                out["summary"] = _fallback_summary(cols, rows) + f" [llm summary unavailable: {e}]"
    except Exception as e:
        out["error"] = str(e)
    finally:
        con.close()
    _log_request(question, intent, attempts_used, round((time.time() - t_start) * 1000),
                 out["error"], request_id)
    return out

# ---------------------------------------------------------------------------
def _print_human(res):
    print(f"\n[intent] {res['intent']}")
    if res["error"]:
        print(f"[error] {res['error']}")
        if res["sql"]: print(f"[sql]\n{res['sql']}")
        return
    print(f"\nSQL\n{'-'*60}\n{res['sql']}")
    if res["summary"]:
        print(f"\nANSWER\n{'-'*60}\n{res['summary']}")
    print(f"\n--- data ({res['row_count']} rows) ---")
    if res["rows"]:
        print(" | ".join(res["columns"]))
        for r in res["rows"][:50]:
            print(" | ".join(str(r[c]) for c in res["columns"]))

def warmup():
    try:
        requests.post(OLLAMA_URL, json={"model": SQL_MODEL, "prompt": "ok",
            "stream": False, "keep_alive": KEEP_ALIVE}, timeout=LLM_TIMEOUT)
        print("model warmed up")
    except Exception as e:
        print(f"warmup skipped: {e}")

def serve(port):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    warmup()
    class H(BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        def do_OPTIONS(self):
            self.send_response(204); self._cors(); self.end_headers()
        def do_POST(self):
            if self.path == "/ask":
                n = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(n) or "{}")
                except Exception:
                    body = {}
                q = (body.get("question") or "").strip()
                summ = body.get("summarize", True)
                res = answer(q, summarize_result=summ) if q else {"error": "no question"}
                payload = json.dumps(res, default=str).encode()
                try:
                    self.send_response(200); self.send_header("Content-Type", "application/json")
                    self._cors(); self.end_headers(); self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # client gave up before we finished
                return

            if self.path == "/feedback":
                n = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(n) or "{}")
                except Exception:
                    body = {}
                ok = _log_feedback(body)
                payload = json.dumps({"ok": ok}).encode()
                try:
                    self.send_response(200 if ok else 400)
                    self.send_header("Content-Type", "application/json")
                    self._cors(); self.end_headers(); self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            self.send_response(404); self._cors(); self.end_headers()
        def log_message(self, *a): pass
    print(f"Traffic QA serving on http://0.0.0.0:{port}/ask      (POST JSON {{'question': ...}})")
    print(f"                  and http://0.0.0.0:{port}/feedback (POST JSON {{'request_id','panel_id','rating','comment'}})")
    print(f"Logging requests to {LOG_FILE}")
    print(f"Logging feedback to {FEEDBACK_LOG_FILE}")
    HTTPServer(("0.0.0.0", port), H).serve_forever()

def main():
    global DB_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-summary", action="store_true")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    DB_PATH = args.db
    if not os.path.exists(DB_PATH):
        sys.exit(f"DB not found: {DB_PATH} (set TRAFFIC_DB or --db)")
    if args.serve:
        serve(args.port); return
    q = " ".join(args.question).strip()
    if not q:
        print("Traffic QA — ask a traffic question. 'exit' to quit.")
        while True:
            try: q = input("\nqa> ").strip()
            except (EOFError, KeyboardInterrupt): break
            if q.lower() in ("exit", "quit"): break
            if q: _print_human(answer(q, not args.no_summary))
        return
    res = answer(q, not args.no_summary)
    print(json.dumps(res, indent=2, default=str) if args.json else None) if args.json else _print_human(res)

if __name__ == "__main__":
    main()