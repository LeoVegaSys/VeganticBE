def _print_human(res: dict):
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