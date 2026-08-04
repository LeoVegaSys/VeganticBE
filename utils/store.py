from uuid import uuid4

from langgraph.store.redis import RedisStore

from config import REDIS_HOST, REDIS_PORT, REDIS_TTL, \
    KEEP_FIRST_N, KEEP_LAST_N, KEEP_THRESHOLD


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
                    sorted = sorted(results, key=lambda x: x.updated_at)
                    for s in sorted[KEEP_FIRST_N: -KEEP_LAST_N]:
                        store.delete(ns, key=s.key)
        
    except Exception as e:
        print(f"Error occurred during store read : {str(e)}")
        return False


def write_entry_to_store(user_id:str, category: str, param:str, data: str):
    try:
        with RedisStore.from_conn_string(REDIS_STORE_URI) as store:
            store.put(
                namespace=(category, user_id),
                key=str(uuid4()),
                value={param : data}
            )
    except Exception as e:
        print(f"Error occurred during store read : {str(e)}")


def clear_store(user_id: str):
    try:
        with RedisStore.from_conn_string(REDIS_STORE_URI) as store:
            namespaces = store.list_namespaces(suffix=(user_id,))
            for ns in namespaces:
                results = store.search(ns, limit=50)
                print(f"store :: clear :: UID {user_id} :: NS {ns} :: LEN {len(results)}")
                for r in results:
                    store.delete(ns, key=r.key)
    except Exception as e:
        print(f"Error occurred during store read : {str(e)}")


def read_from_store(user_id: str, category: str, params: list[str]) -> list[dict]:
    result_set = []
    try:
        with RedisStore.from_conn_string(REDIS_STORE_URI) as store:
            namespace = (category, user_id)
            results = store.search(namespace, limit=50)
            print(f"store :: read :: UID {user_id} :: NS {namespace} :: LEN {len(results)}")
            if results:
                result_set = [r.value for r in results for p in params if p in r.value]
            return result_set
    except Exception as e:
        print(f"Error occurred during store write : {str(e)}")
        return []