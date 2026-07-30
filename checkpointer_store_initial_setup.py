from langgraph.store.redis import RedisStore
from langgraph.checkpoint.redis import RedisSaver

from config import REDIS_HOST, REDIS_PORT


def main():
    """
    To be performed ONLY ONCE, to set up database schema migrations in REDIS
    RUN before first usage of checkpoint or store in langgraph
    """
    redis_uri = f"redis://{REDIS_HOST}:{REDIS_PORT}"
    with RedisStore.from_conn_string(redis_uri) as store:
        store.setup()
        
        with RedisSaver.from_conn_string(redis_uri) as checkpointer:
            checkpointer.setup()


if __name__ == "__main__":
    main()