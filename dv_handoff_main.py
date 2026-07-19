from dotenv import load_dotenv
load_dotenv()

import os
import sys
import json
import argparse

from graph.graph_manager import WorkflowManager
from server.apis import serve


"""
def main():
    # for deployment on langgraph cloud
    # graph = WorkflowManager().returnGraph()
    while True:
        question=input("Enter your question here (Enter `quit` to exit) :")
        if question.strip().lower() == "quit":
            break
        answer=WorkflowManager().run_sql_agent(question)
        print(f"\nQ : {question}\nA : {answer}\n")
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("--db", default=os.environ.get("DB_PATH"))
    ap.add_argument("--db-type", default=os.environ.get("MCP_DB_TYPE"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-summary", action="store_true")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=os.environ.get("SERVER_PORT"))
    args = ap.parse_args()
    DB_PATH = args.db
    if not os.path.exists(DB_PATH):
        sys.exit(f"DB not found: {DB_PATH} (set TRAFFIC_DB or --db)")
    if args.serve:
        serve(args.port); return
    q = " ".join(args.question).strip()
    graph = WorkflowManager()
    if not q:
        print("Traffic QA — ask a traffic question. 'exit' to quit.")
        while True:
            try: q = input("\nqa> ").strip()
            except (EOFError, KeyboardInterrupt): break
            if q.lower() in ("exit", "quit"): break
            # if q: _print_human(answer(q, not args.no_summary))
            if q: print(graph.run_sql_agent(q, not args.no_summary))
        return
    # res = answer(q, not args.no_summary)
    res = graph.run_sql_agent(q)
    print(json.dumps(res, indent=2, default=str) if args.json else None) if args.json else print(res)




if __name__ == "__main__":
    main()