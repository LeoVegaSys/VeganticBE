from langgraph.store.redis import RedisStore

from config import REDIS_HOST, REDIS_PORT, REDIS_TTL, \
    KEEP_FIRST_N, KEEP_LAST_N, KEEP_THRESHOLD, \
    HISTORY, WARMUP, OLLAMA_KEEP_ALIVE


REDIS_STORE_URI = f"redis://{REDIS_HOST}:{REDIS_PORT}"


def get_store_config():
    return {
    "default_ttl": int(REDIS_TTL),      # Expire data after REDIS_TTL minutes
    "refresh_on_read": True             #TRUE to Reset expiration timer on each read
}


def manage_store(user_id: str):
    """
    Clear older records. Store size max KEEP_THRESHOLD
    Check counts of each namespace, Sort by updated_at asc
    Keep first KEEP_FIRST_N and latest KEEP_LAST_N
    """
    try:
        with RedisStore.from_conn_string(REDIS_STORE_URI) as store:
            namespaces = store.list_namespaces(suffix=(user_id,))
            for ns in namespaces:
                results = store.search(ns, limit=50)
                print(f"store :: manage :: UID {user_id} :: NS {ns} :: LEN {len(results)}")
                if len(results) > KEEP_THRESHOLD:
                    r_sorted = sorted(results, key=lambda x: x.updated_at)
                    for s in r_sorted[KEEP_FIRST_N: -KEEP_LAST_N]:
                        store.delete(ns, key=s.key)
        
    except Exception as e:
        print(f"Error occurred during store read : {str(e)}")
        return False


def write_entry_to_store(user_id: str, category: str, param: str, data: str):
    from uuid import uuid4
    try:
        with RedisStore.from_conn_string(REDIS_STORE_URI) as store:
            store.put(
                namespace=(category, user_id),
                key=str(uuid4()),
                value={param : data}
            )
    except Exception as e:
        print(f"Error occurred during store write : {str(e)}")


def clear_store(user_id: str, category: str = ""):
    """
    If category is provided, deletes all category records ONLY for user.
    If category is not provided, deletes all store records for ALL categories for user.
    """
    try:
        with RedisStore.from_conn_string(REDIS_STORE_URI) as store:
            if category:
                namespaces = [(category, user_id)]
            else:
                namespaces = store.list_namespaces(suffix=(user_id,))
            for ns in namespaces:
                results = store.search(ns, limit=50)
                print(f"store :: clear :: UID {user_id} :: NS {ns} :: LEN {len(results)}")
                for r in results:
                    store.delete(ns, key=r.key)
    except Exception as e:
        print(f"Error occurred during store read : {str(e)}")


def read_from_store(user_id: str, category: str, params: list[str] = []) -> list[dict]:
    """
    If params is provided, Returns category records matching the list of text params.
    If params is not provided, Returns all records for the category.
    """
    result_set = []
    try:
        with RedisStore.from_conn_string(REDIS_STORE_URI) as store:
            namespace = (category, user_id)
            results = store.search(namespace, limit=50)
            print(f"store :: read :: UID {user_id} :: NS {namespace} :: LEN {len(results)}")
            if results:
                if params:
                    result_set = [r for r in results for p in params if p in r.value]
                else:
                    result_set = [r for r in results]
            return result_set
    except Exception as e:
        print(f"Error occurred during store write : {str(e)}")
        return []


def get_conversation_history(user_id: str, params: list[str]) -> str:
    """
    Returns key-value pairs in flattened string, stored as part of previous conversations 
    """
    history = ""
    if not warmup_done(user_id):
        memories = read_from_store(user_id=user_id, category=HISTORY, params=params)
        if memories:
            history = "\n".join([f"{k.upper()}:{v}" for m in memories for k,v in m.value.items()])
        print(f"GCM :: store :: {HISTORY}, {user_id} :: MemLen :: {len(memories)}")
        write_entry_to_store(user_id=user_id, category=WARMUP, param="warmup", data="true")
    return history


def warmup_done(user_id: str):
    """Returns True if warmup has been performed in last 30 mins"""
    from datetime import datetime, timezone
    warmed_up = False
    # Check if warmup prompt already loaded
    warmup_done = read_from_store(user_id=user_id, category=WARMUP)
    if warmup_done:
        keep_alive_mins = get_keep_alive_in_mins()
        last_run = warmup_done[0].updated_at.replace(tzinfo=timezone.utc)
        mins_since_last_run = ((datetime.now(timezone.utc) - last_run).total_seconds())//60
        if mins_since_last_run > keep_alive_mins:
            print(f"Warmup completed for user {user_id} more than {keep_alive_mins} mins ago.")
        else:
            print(f"Warmup already completed for user {user_id}.")
            warmed_up = True
    if not warmed_up:   # CLEAR OLD WARMUP ENTRIES IF ANY
        print(f"Warmup not completed for user {user_id}.")
        clear_store(user_id=user_id, category=WARMUP)
    return warmed_up


def get_keep_alive_in_mins():
    import re
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
    is_alphanum = any(c.isalpha() for c in OLLAMA_KEEP_ALIVE)
    if is_alphanum:
        total_seconds = sum(
            int(value) * units[unit.lower()] 
            for value, unit in re.findall(r'(\d+)([dhmshw])', OLLAMA_KEEP_ALIVE)
        )
        return (total_seconds//60)
    else:
        return int(OLLAMA_KEEP_ALIVE)