from uuid import uuid4

from langgraph.store.redis import RedisStore

from config import REDIS_HOST, REDIS_PORT, REDIS_TTL

REDIS_STORE_URI = f"redis://{REDIS_HOST}:{REDIS_PORT}"


def get_store_config():
    return {
    "default_ttl": int(REDIS_TTL),      # Expire data after REDIS_TTL minutes
    "refresh_on_read": True             #TRUE to Reset expiration timer on each read
}

def write_entry_to_store(store:RedisStore, user_id:str, category: str, param:str, data: str):
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
    with RedisStore.from_conn_string(REDIS_STORE_URI) as store:

        # CLEAR ALL NAMESPACES RELATED TO USER
        pass

def read_from_store(store: RedisStore, user_id: str, category: str, params: list[str]) -> list[dict]:
    result_set = []
    try:
        with RedisStore.from_conn_string(REDIS_STORE_URI) as store:
            namespace = (category, user_id)
            results = store.search(namespace)
            if results:
                result_set = [r.value for r in results for p in params if p in r.value]
            return result_set
    except Exception as e:
        print(f"Error occurred during store write : {str(e)}")
        return []