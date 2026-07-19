import os
from dotenv import load_dotenv
load_dotenv()
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from logs.user_logs import FileLogger
from graph.graph_manager import WorkflowManager
    

class ApiServer(BaseHTTPRequestHandler):
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
            db_type = body.get("db_type", os.environ.get("MCP_DB_TYPE"))
            # res = WorkflowManager().run_sql_agent(q, summarize_result=summ) if q else {"error": "no question"}
            res = WorkflowManager().run_sql_agent(question=q, db_type=db_type, summarize=summ) if q else {"error": "no question"}
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
            # ok = _log_feedback(body)
            ok = FileLogger().write_to_log(line=body, feedback=True)
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


def serve(port):
    host=os.environ.get("SERVER_HOST","localhost")
    print(f"Traffic QA serving on http://{host}:{port}/ask      (POST JSON {{'question': ...}})")
    print(f"                  and http://{host}:{port}/feedback (POST JSON {{'request_id','panel_id','rating','comment'}})")
    print(f'Logging requests to {os.environ.get("QA_LOG_FILE")}')
    print(f'Logging feedback to {os.environ.get("QA_FEEDBACK_LOG_FILE")}')
    HTTPServer((host, port), ApiServer).serve_forever()
