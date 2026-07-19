from langgraph.types import Command

from database.db_manager import DatabaseManager
from models.llm_manager import LLMManager_REST
from utils.skill_loader import get_skills_content
from config import CHART_INTENT_ALIASES, MCP_DB_TYPE, BUSINESS_FACTS, \
SUMMARY_MODEL, SQL_MODEL, TRAFFIC_TABLE_NAME, QA_MAX_REPAIRS


# Miscellaneous Query Modification Logic
def clean_sql(query: str) -> str:
    return query.replace("```sql", "").replace("```", "").strip().rstrip(";").strip()

def intent_tag(q):
    ql = q.lower()
    if any(w in ql for w in ("how many", "count", "number of")): return "count"
    if any(w in ql for w in ("top", "highest", "lowest", "busiest", "rank", "most", "least")): return "ranking"
    if any(w in ql for w in ("util", "congest", "capacity")): return "utilization"
    if any(w in ql for w in ("average", "avg", "total", "sum", "per ")): return "aggregation"
    if any(w in ql for w in ("over time", "trend", "by time", "each hour", "timeline")): return "timeseries"
    return "lookup"

def max_min_time_query(table_name: str) -> str:
    return f'SELECT MIN("Time"), MAX("Time") FROM {table_name}'

def link_type_query(table_name: str) -> str:
    return f'SELECT DISTINCT "LinkType" FROM {table_name}'

def sql_generate_prompt(db_type, business_facts, table_name, schema, lts, when, question):
    return f"""You are an expert telecom analyst writing {db_type} SQL.
{business_facts}
LIVE SCHEMA of table `{table_name}`:
{schema}
Valid "LinkType" values: {lts}
Data time range: {when}
Write ONE DuckDB SQL query that answers the question.
Return ONLY the SQL — no markdown, no comments, no explanation.
If there is not enough information to write a SQL query, respond with "NOT_ENOUGH_INFO".
Question: {question}
"""

def sql_repair_prompt(db_type, business_facts, schema, question, bad_sql, err):
    return f"""Fix this {db_type} SQL. Return ONLY corrected SQL.
{business_facts}
SCHEMA: {schema}
QUESTION: {question}
BROKEN SQL: {bad_sql}
ERROR: {err}
If there is not enough information to write a SQL query, respond with "NOT_ENOUGH_INFO".
Corrected SQL:"""


def sql_summarize_prompt(question, cols, preview):
    return f"""You are a telecom NOC analyst. Answer the question from the result ONLY.
Respond in ENGLISH, 2-4 sentences. Name the key entities with their numbers.
Convert Kbps to Mbps/Gbps when large. Flag utilization > 100 as a likely stale-BW issue.
Do not restate the whole table or explain the SQL.

QUESTION: {question}
COLUMNS: {cols}
ROWS: {preview}
"""


class TrafficAgent:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.llm_manager_rest = LLMManager_REST()
        self.db_type = MCP_DB_TYPE
        self.business_facts = get_skills_content(skills_file_name=BUSINESS_FACTS)
    

    def repair_sql(self, state: dict) -> dict:
        """Validate and fix SQL"""
        retries = state["repairs_left"]
        ### If retries are left or issues raised in prior run, rerun loop at generate sql func
        has_sql_faults = state["sql_issues"] or state["error"]
        if retries and not state["sql_valid"] and has_sql_faults:
            return Command(
                goto="generate_sql",
                update={"repairs_left": retries - 1}
            )
        ### If retries are over or no issues remaining, continue to summarize func
        return Command(
            goto="summarize",
            update={"repairs_left": 0}
        )
    

    def generate_sql(self, state: dict) -> dict:
        """Create/Corrects SQL query for provided user question"""
        question = state["question"]
        self.schema = self.db_manager.get_schema(uuid=state["request_id"])
        do_repair = False   #Manages SQL correction

        if state["sql_query"] and (state["error"] or state["sql_issues"]):
            sql_faults = f'{state["error"]}\nIssues:{state["sql_issues"]}\n'
            do_repair = True

        if do_repair:
            prompt = sql_repair_prompt(
                db_type=self.db_type, business_facts=self.business_facts,
                schema=self.schema, question=question,
                bad_sql=state["sql_query"], err=sql_faults
            )
        else:
            table_name = TRAFFIC_TABLE_NAME
            lts = self.execute_sql(state, alt_query=link_type_query(table_name=table_name))
            when = self.execute_sql(state, alt_query=max_min_time_query(table_name=table_name))

            prompt = sql_generate_prompt(
                db_type=self.db_type, business_facts=self.business_facts,
                table_name=table_name, schema=self.schema,
                lts=lts, when=when, question=question,
            )
        
        sql_response = clean_sql(
            self.llm_manager_rest.call(
                prompt=prompt, model=SQL_MODEL, temperature=0.0
            ))
    
        if sql_response.strip() == "NOT_ENOUGH_INFO":
            return {"sql_query": "NOT_RELEVANT"}
        else:
            return {"sql_query": sql_response, "sql_valid": True, "sql_issues": "", "error": ""}


    def summarize(self, state: dict) -> dict:
        """Provide summary for user question"""
        question = state["question"]
        if state["sql_query"] == "NOT_RELEVANT":
            return {"answer": f'Sorry, Please provide additional information. Original question : {question}'}

        #Dummy placeholders
        cols = preview = []

        try:
            summary = self.llm_manager_rest.call(
                prompt=sql_summarize_prompt(question, cols, preview),
                model=SUMMARY_MODEL,
                temperature=0.2
            )
        except Exception as e:
            summary = f"LLM summary unavailable. Issue encountered : {e}"
        return {"summary": summary}

    def warmup(self, state: dict) -> dict:
        intent = intent_tag(state["question"])

        self.llm_manager_rest.call(warmup=True)
        
        return {
            "repairs_left": QA_MAX_REPAIRS, 
            "intent": intent,
            "chart_intent" : CHART_INTENT_ALIASES.get(intent, intent)
        }
    

    def run_sql(self, state: dict, query: str) -> dict:
        """Execute query"""
        query = state["sql_query"].lower().lstrip()
        if state["sql_query"] == "NOT_RELEVANT":
            return {"sql_valid": False}
        
        if not (query.startswith("select") or query.startswith("with")):
            return {
                "sql_valid": False,
                "sql_issues": "Only read-only SELECT/WITH queries are allowed."
            }
        
        try:
            result = self.execute_sql(state)
            return {"sql_valid": True, "results": result}
        except Exception as e:
            return {"error": str(e)}
    

    def execute_sql(self, state: dict, alt_query: str = None) -> dict:
        """Execute SQL query and return results."""
        print(f"execute_sql :: state : {state} :: alt query :: {alt_query}")
        query = alt_query if alt_query else state['sql_query']
        uuid = state['request_id']
        try:
            results = self.db_manager.execute_query(uuid, query)    
            return results
        except Exception as e:
            # return {"error": str(e)}
            raise e