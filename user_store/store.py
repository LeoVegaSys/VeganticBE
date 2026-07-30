from langgraph.store.redis import RedisStore

class UserStore:
    def __init__(self, user_id):
        self.db_uri = ""
        self.user_id = user_id
        self.store = None
        self.store_db = RedisStore.from_conn_string(self.db_uri)

    def write_to_store(self, category: str):
        pass

    def clear_store(self):
        pass

    def read_from_store(self):
        pass