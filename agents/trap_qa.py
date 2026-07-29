#!/usr/bin/env python3
"""
Trap QA Agent - FULLY DYNAMIC (no structured builder) + conversational memory.
============================================================================
Flow per request:
    question (+ filters + session_id)
      -> LLM classify: intent + is_follow_up + wants_count
      -> follow-up? inherit prior filters (UI filters still win)
      -> schema context (columns + categories + real circles + time range)
      -> LLM generate SQL  (dynamic; no templates)
      -> repair loop (<=2) on SQL error
      -> LLM review: does the result answer the question?
             not ok + fix -> regenerate once with the hint
             ok           -> smart summary (only if rows > 0)
      -> record turn in session memory (last 3 turns)

/ask   {"question","filters","session_id","summarize"}
/reset {"session_id"}
/feedback {"request_id","rating","comment"}

Usage:
    python Trap_Qa.py "which circles have the most outages"
    python Trap_Qa.py --serve --port 5056
"""
import os, re, sys, json, time, uuid, argparse, requests
import mysql.connector

# ---------------- config ----------------
OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
SQL_MODEL   = os.environ.get("QA_MODEL", "qwen2.5-coder:7b")
SUM_MODEL   = os.environ.get("QA_SUM_MODEL", "llama3.2:3b")
LLM_TIMEOUT = int(os.environ.get("QA_TIMEOUT", "180"))
KEEP_ALIVE  = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
ROW_LIMIT   = int(os.environ.get("QA_ROW_LIMIT", "500"))
MAX_SQL_REPAIRS  = int(os.environ.get("QA_MAX_REPAIRS", "2"))
MAX_REVIEW_LOOPS = int(os.environ.get("QA_MAX_REVIEW", "1"))
MEMORY_TURNS     = int(os.environ.get("QA_MEMORY_TURNS", "3"))
TABLE = "PORT_TRAFFIC_TRAP_RESULT"

LOG_FILE      = os.environ.get("QA_LOG_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_log.jsonl"))
FEEDBACK_FILE = os.environ.get("QA_FEEDBACK_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_feedback.jsonl"))

DB_CONFIG = {
    "host":     os.environ.get("ANALYTICS_DB_HOST", "localhost"),
    "user":     os.environ.get("ANALYTICS_DB_USER", "trap_qa_svc"),
    "password": os.environ.get("ANALYTICS_DB_PASS", ""),
    "database": os.environ.get("ANALYTICS_DB_NAME", "Vegayan_Topo_79_AI"),
}

def _load_facts():
    path = os.environ.get("QA_BUSINESS_FACTS",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "business_facts.md"))
    try:
        return open(path).read()
    except Exception as e:
        print(f"[warn] business_facts.md not loaded: {e}")
        return "(business_facts.md not found)"
BUSINESS_FACTS = _load_facts()

INTENTS = ["count","count_by","ranking","util_band","transition",
           "distinct_list","base_traffic","lookup","exploratory"]
CHART_HINT = {"count":"kpi","count_by":"bar","ranking":"bar","util_band":"table",
              "transition":"table","distinct_list":"table","base_traffic":"table",
              "lookup":"table","exploratory":"table"}

# ---------------- conversational memory ----------------
_SESSIONS = {}
def mem_get(sid):  return _SESSIONS.get(sid, []) if sid else []
def mem_add(sid, turn):
    if not sid: return
    h = _SESSIONS.setdefault(sid, [])
    h.append(turn); del h[:-MEMORY_TURNS]
def mem_reset(sid): _SESSIONS.pop(sid, None)

# ---------------- LLM plumbing ----------------
def _call(model, prompt, temperature=0.0):
    r = requests.post(OLLAMA_URL, json={"model": model, "prompt": prompt,
        "stream": False, "temperature": temperature, "keep_alive": KEEP_ALIVE},
        timeout=LLM_TIMEOUT)
    r.raise_for_status()
    return r.json()["response"]

def _json_from(text):
    t = text.strip().replace("```json","").replace("```","")
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < 0:
        raise ValueError(f"no JSON in model reply: {text[:120]}")
    return json.loads(t[a:b+1])

def _clean_sql(s):
    s = s.replace("```sql","").replace("```","").strip()
    m = re.search(r"\b(SELECT|WITH)\b", s, re.I)
    if m: s = s[m.start():]
    return s.strip().rstrip(";").strip()

def llm_classify(question, history, filters):
    hist = "\n".join(f"- Q:{h['question']} (intent:{h['intent']})" for h in history[-3:]) or "(none)"
    prompt = f"""You classify a telecom NOC analytics question. Reply ONLY JSON.

Recent conversation (most recent last):
{hist}

Current UI filters: {json.dumps(filters or {})}
Question: {question}

Return JSON:
{{"intent": one of {INTENTS},
  "is_follow_up": true/false,
  "wants_count": true/false,
  "notes": "one short phrase"}}

Guidance:
- "which circles/categories have the most X" = count_by (GROUP BY), NOT ranking.
- "how many / number of" = count. "list / show all" = lookup or distinct_list.
- utilization bands = util_band. zero<->active traffic changes = transition.
- traffic before outage / base traffic = base_traffic. Open-ended = exploratory.
- is_follow_up = true only if the question refers back to a prior turn
  (e.g. "those", "that circle", "same but inactive")."""
    return _json_from(_call(SQL_MODEL, prompt, 0.0))

def llm_generate_sql(question, history, filters, schema, cls, review_hint):
    hist = "\n".join(f"- {h['question']} -> {h['sql']}" for h in history[-2:] if h.get('sql')) or "(none)"
    hint = f"\nA reviewer flagged the previous attempt: {review_hint}\nFix accordingly." if review_hint else ""
    fpart = (f"\nApply these as WHERE constraints (circle matches trap_src LIKE '%value%'):\n{json.dumps(filters)}"
             if filters else "")
    prompt = f"""You are an expert MySQL 5.7 analyst for a telecom NOC. Write ONE query.

{BUSINESS_FACTS}

{schema}

Recent turns (for follow-up context):
{hist}

Intent: {cls.get('intent')}   wants_count: {cls.get('wants_count')}{fpart}{hint}

Question: {question}

Rules: MySQL 5.7 (NO CTEs/WITH - use subqueries). Return ONLY the SQL, no prose.
If wants_count is true, return COUNT(...) not a row list.
Wrap any OR group in parentheses so other filters are not dropped."""
    return _clean_sql(_call(SQL_MODEL, prompt, 0.0))

def llm_repair(question, bad_sql, err, schema):
    prompt = f"""Fix this MySQL 5.7 query. Return ONLY corrected SQL.
{schema}
QUESTION: {question}
BROKEN SQL: {bad_sql}
ERROR: {err}
Remember: no CTEs in 5.7; parenthesize OR groups. Corrected SQL:"""
    return _clean_sql(_call(SQL_MODEL, prompt, 0.0))

def llm_review(question, sql, cols, rows, filters):
    preview = json.dumps(rows[:10], default=str)[:1500]
    prompt = f"""You review whether a SQL result ANSWERS the question. Reply ONLY JSON.

Question: {question}
Filters that should be applied: {json.dumps(filters or {})}
SQL: {sql}
Columns: {cols}
Sample rows: {preview}

Return JSON:
{{"ok": true/false,
  "notes": "one short phrase",
  "suggested_fix": "if not ok, a SHORT instruction to fix the SQL, else empty"}}

Fail (ok=false) if the query shape doesn't match the question (e.g. asked a count
of circles but got a list of links), a requested filter is missing, or an OR
clause dropped a filter. Otherwise ok=true."""
    try:
        return _json_from(_call(SQL_MODEL, prompt, 0.0))
    except Exception:
        return {"ok": True, "notes": "review skipped", "suggested_fix": ""}

def llm_summarize(question, sql, cols, rows, intent):
    preview = json.dumps(rows[:40], default=str)[:2500]
    prompt = f"""You are a telecom NOC analyst. Answer the question from the result ONLY.
2-4 sentences, English. Name key links/circles with their numbers.
Values are decimal-MB volumes, NOT Gbps. confidence=2 means lower-confidence/reversed.
Do not restate the whole table or the SQL.

QUESTION: {question}
INTENT: {intent}
COLUMNS: {cols}
ROWS: {preview}"""
    return _call(SUM_MODEL, prompt, 0.2).strip()

# ---------------- DB ----------------
def _con():
    return mysql.connector.connect(**DB_CONFIG)

def schema_context():
    con = _con()
    try:
        cur = con.cursor(buffered=True)
        cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                       WHERE table_name=%s AND table_schema=%s ORDER BY ordinal_position""",
                    (TABLE, DB_CONFIG["database"]))
        schema = ", ".join(f"`{c}` {t}" for c, t in cur.fetchall())
        cur.execute(f"SELECT DISTINCT category FROM {TABLE} WHERE category IS NOT NULL")
        cats = [r[0] for r in cur.fetchall()]
        cur.execute(f"SELECT DISTINCT trap_src FROM {TABLE} WHERE trap_src IS NOT NULL LIMIT 40")
        circles = [r[0] for r in cur.fetchall()]
        try:
            cur.execute(f"SELECT MIN(event_time), MAX(event_time) FROM {TABLE}")
            mn, mx = cur.fetchone(); when = f"{mn} -> {mx}"
        except Exception:
            when = "n/a"
        cur.close()
        return (f"LIVE SCHEMA of `{TABLE}`:\n{schema}\n\n"
                f"Valid `category` values: {cats}\n"
                f"Example `trap_src` (circle) values: {circles}\n"
                f"event_time range: {when}")
    finally:
        con.close()

def run_sql(sql):
    low = sql.lower().lstrip()
    if not (low.startswith("select") or low.startswith("with")):
        raise ValueError("Only read-only SELECT/WITH queries are allowed.")
    con = _con()
    try:
        cur = con.cursor(buffered=True)     # buffered -> never 'Unread result found'
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [{c: (str(v) if hasattr(v, "isoformat") else v)
                 for c, v in zip(cols, r)} for r in cur.fetchmany(ROW_LIMIT)]
        cur.close()
        return cols, rows
    finally:
        con.close()

# ---------------- filter merge ----------------
def merge_filters(ui_filters, prev_filters, use_prev):
    merged = dict(prev_filters) if use_prev and prev_filters else {}
    for k, v in (ui_filters or {}).items():
        if v not in (None, "", []):
            merged[k] = v
    return merged

# ---------------- the agent ----------------
def answer(question=None, filters=None, session_id=None, summarize=True):
    t0 = time.time()
    rid = uuid.uuid4().hex[:12]
    history = mem_get(session_id)
    out = {"request_id": rid, "question": question, "filters": filters,
           "session_id": session_id, "intent": None, "chart_intent": None,
           "path": "dynamic", "follow_up": bool(history), "effective_filters": None,
           "sql": None, "columns": [], "rows": [], "row_count": 0,
           "review_notes": None, "summary": None, "error": None}

    if not question:
        out["error"] = "no question provided"; return out

    # 1. INTENT
    try:
        cls = llm_classify(question, history, filters)
    except Exception as e:
        out["error"] = f"intent classification failed: {e}"
        _log(out, t0); return out
    out["intent"] = cls.get("intent")
    out["chart_intent"] = CHART_HINT.get(cls.get("intent"), "table")
    is_follow_up = bool(cls.get("is_follow_up"))

    # 2. filter inheritance on follow-ups (UI wins)
    prev_filters = history[-1].get("effective_filters") if history else None
    eff = merge_filters(filters, prev_filters, is_follow_up)
    out["effective_filters"] = eff

    # 3. schema
    try:
        schema = schema_context()
    except Exception as e:
        out["error"] = f"schema fetch failed: {e}"; _log(out, t0); return out

    # 4. generate -> repair -> review
    review_loops, review_hint = 0, None
    while True:
        try:
            sql = llm_generate_sql(question, history, eff, schema, cls, review_hint)
        except Exception as e:
            out["error"] = f"sql generation failed: {e}"; break
        out["sql"] = sql

        cols, rows, err = _exec_with_repair(question, sql, schema, out)
        if err:
            out["error"] = err; break
        out["columns"], out["rows"], out["row_count"] = cols, rows, len(rows)

        if review_loops < MAX_REVIEW_LOOPS:
            verdict = llm_review(question, out["sql"], cols, rows[:20], eff)
            out["review_notes"] = verdict.get("notes")
            if not verdict.get("ok", True) and verdict.get("suggested_fix"):
                review_hint = verdict["suggested_fix"]; review_loops += 1
                continue
        break

    # 5. summary (only if rows and no error)
    if out["error"] is None:
        if out["row_count"] == 0:
            out["summary"] = "No rows matched this query."
        elif summarize:
            try:
                out["summary"] = llm_summarize(question, out["sql"], out["columns"],
                                               out["rows"], out["intent"])
            except Exception as e:
                out["summary"] = f"({out['row_count']} rows; summary unavailable)"

    # 6. memory
    mem_add(session_id, {"question": question, "intent": out["intent"],
                         "sql": out["sql"], "effective_filters": eff,
                         "row_count": out["row_count"]})
    _log(out, t0)
    return out

def _exec_with_repair(question, sql, schema, out):
    cur_sql = sql
    for attempt in range(MAX_SQL_REPAIRS + 1):
        try:
            cols, rows = run_sql(cur_sql)
            out["sql"] = cur_sql
            return cols, rows, None
        except Exception as e:
            if attempt == MAX_SQL_REPAIRS:
                return [], [], f"SQL failed after {attempt} repair(s): {e}"
            try:
                cur_sql = llm_repair(question, cur_sql, str(e), schema)
            except Exception as e2:
                return [], [], f"repair failed: {e2}"
            out["sql"] = cur_sql
    return [], [], "unreachable"

# ---------------- logging ----------------
def _log(res, t0):
    res["total_ms"] = round((time.time()-t0)*1000)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "request_id": res.get("request_id"), "session_id": res.get("session_id"),
                "question": res.get("question"), "intent": res.get("intent"),
                "follow_up": res.get("follow_up"), "review_notes": res.get("review_notes"),
                "row_count": res.get("row_count"), "total_ms": res.get("total_ms"),
                "error": res.get("error")}, default=str) + "\n")
    except Exception:
        pass

def _log_feedback(body):
    try:
        rating = (body.get("rating") or "").lower()
        if rating not in ("up","down"): return False
        with open(FEEDBACK_FILE, "a") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "request_id": body.get("request_id"), "rating": rating,
                "comment": (body.get("comment") or "")[:2000]}, default=str) + "\n")
        return True
    except Exception:
        return False

# ---------------- CLI / server ----------------
def _print_human(r):
    print(f"\n[intent] {r['intent']}  [path] {r['path']}  [follow_up] {r['follow_up']}  [{r.get('total_ms')}ms]")
    if r.get("effective_filters"): print(f"[filters] {r['effective_filters']}")
    if r["error"]:
        print(f"[error] {r['error']}")
        if r["sql"]: print(f"[sql]\n{r['sql']}")
        return
    if r["review_notes"]: print(f"[review] {r['review_notes']}")
    if r["sql"]: print(f"\nSQL\n{'-'*60}\n{r['sql']}")
    if r["summary"]: print(f"\nANSWER\n{'-'*60}\n{r['summary']}")
    print(f"\n--- data ({r['row_count']} rows) ---")
    if r["rows"]:
        print(" | ".join(r["columns"]))
        for row in r["rows"][:30]:
            print(" | ".join(str(row.get(c)) for c in r["columns"]))

def serve(port):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class H(BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin","*")
            self.send_header("Access-Control-Allow-Headers","Content-Type")
            self.send_header("Access-Control-Allow-Methods","POST, OPTIONS")
        def _send(self, code, obj):
            b = json.dumps(obj, default=str).encode()
            try:
                self.send_response(code); self.send_header("Content-Type","application/json")
                self._cors(); self.end_headers(); self.wfile.write(b)
            except (BrokenPipeError, ConnectionResetError): pass
        def do_OPTIONS(self): self.send_response(204); self._cors(); self.end_headers()
        def do_POST(self):
            n = int(self.headers.get("Content-Length",0))
            try: body = json.loads(self.rfile.read(n) or "{}")
            except Exception: body = {}
            if self.path == "/ask":
                q = (body.get("question") or "").strip() or None
                if not q: return self._send(400, {"error":"'question' required"})
                return self._send(200, answer(q, body.get("filters"),
                                              body.get("session_id"),
                                              body.get("summarize", True)))
            if self.path == "/reset":
                mem_reset(body.get("session_id")); return self._send(200, {"ok": True})
            if self.path == "/feedback":
                ok = _log_feedback(body); return self._send(200 if ok else 400, {"ok": ok})
            self._send(404, {"error":"not found"})
        def log_message(self,*a): pass
    print(f"Trap QA (dynamic + memory) on http://0.0.0.0:{port}/ask  /reset  /feedback")
    print(f"DB: {DB_CONFIG['database']}@{DB_CONFIG['host']}  table {TABLE}")
    print(f"models: sql={SQL_MODEL} summary={SUM_MODEL}  (no structured path - fully dynamic)")
    HTTPServer(("0.0.0.0", port), H).serve_forever()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("--filters"); ap.add_argument("--session", default="cli")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-summary", action="store_true")
    ap.add_argument("--serve", action="store_true"); ap.add_argument("--port", type=int, default=5056)
    a = ap.parse_args()
    if a.serve: serve(a.port); return
    filters = json.loads(a.filters) if a.filters else None
    q = " ".join(a.question).strip() or None
    if not q:
        print("Trap QA (dynamic). 'exit' to quit.")
        while True:
            try: q = input("\nqa> ").strip()
            except (EOFError, KeyboardInterrupt): break
            if q.lower() in ("exit","quit"): break
            if q: _print_human(answer(q, filters, a.session, not a.no_summary))
        return
    r = answer(q, filters, a.session, not a.no_summary)
    print(json.dumps(r, indent=2, default=str)) if a.json else _print_human(r)

if __name__ == "__main__":
    main()