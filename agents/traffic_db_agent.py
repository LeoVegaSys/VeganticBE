import json

from langgraph.types import Command

from database.db_manager import DatabaseManager
from models.llm_manager import LLMManager_REST
from utils.skill_loader import get_skills_content
from utils.summarizer import get_summarize_prompt, fallback_summarize
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


class TrafficAgent:
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.llm_manager_rest = LLMManager_REST()
        self.business_facts = get_skills_content(skills_file_name=BUSINESS_FACTS)
    

    def repair_sql(self, state: dict) -> dict:
        """Validate and fix SQL"""
        print(f"traffic_agent :: repair_sql :: state :: {state}")
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
    

    def _get_schema(self) -> str:
        """ 
        Returns comma-separated string of concatenated column names and their datatypes 
        """
        query = f"SELECT column_name, data_type FROM information_schema.columns \
        WHERE table_name = '{TRAFFIC_TABLE_NAME}' ORDER BY ordinal_position"
        result = self.db_manager.execute_query(uuid=self.request_id, query=query)
        return ", ".join(f'"{c}" {t}' for c, t in result["rows"])
    

    def _get_link_types(self) -> list:
        """ Returns list of valid link types """
        query = f'SELECT DISTINCT "LinkType" FROM {TRAFFIC_TABLE_NAME}'
        result = self.db_manager.execute_query(uuid=self.request_id, query=query)
        return [r[0] for r in result["rows"] if r[0]]
    
    
    def _get_max_min_time(self) -> str:
        """ Returns max and min time if available else n/a """
        query = f'SELECT MIN("Time"), MAX("Time") FROM {TRAFFIC_TABLE_NAME}'
        try:
            result = self.db_manager.execute_query(uuid=self.request_id, query=query)
            min, max = result["rows"][0]
            return f"{min} -> {max}"
        except Exception as e:
            return "n/a"
        

    def generate_sql(self, state: dict) -> dict:
        """Create/Corrects SQL query for provided user question"""
        print(f"traffic_agent :: generate_sql :: state :: {state}")
        self.request_id = state["request_id"]
        question = state["question"]
        schema = self._get_schema()
        do_repair = False   #Manages SQL correction

        if "sql_query" in state and state["sql_query"] and (state["error"] or state["sql_issues"]):
            sql_faults = f'{state["error"]}\nIssues:{state["sql_issues"]}\n'
            do_repair = True

        if do_repair:
            prompt = sql_repair_prompt(
                db_type=MCP_DB_TYPE, business_facts=self.business_facts,
                schema=schema, question=question,
                bad_sql=state["sql_query"], err=sql_faults
            )
        else:
            lts = self._get_link_types()
            when = self._get_max_min_time()

            prompt = sql_generate_prompt(
                db_type=MCP_DB_TYPE, business_facts=self.business_facts,
                table_name=TRAFFIC_TABLE_NAME, schema=schema,
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
        print(f"traffic_agent :: summarize :: state :: {state}")
        if state["sql_query"] == "NOT_RELEVANT":
            return {"summary": f'Sorry, Please provide additional information. Original question : {state["question"]}'}

        try:
            summary = self.llm_manager_rest.call(
                prompt=get_summarize_prompt(state),
                model=SUMMARY_MODEL,
                temperature=0.2
            )
        except Exception as e:
            summary = fallback_summarize(state["rows"]) + f"\nLLM summary unavailable. Issue encountered : {e}"
        return {"summary": summary}


    def warmup(self, state: dict) -> dict:
        print(f"traffic_agent :: warmup :: state :: {state}")
        intent = intent_tag(state["question"])

        self.llm_manager_rest.call(warmup=True)
        
        return {
            "repairs_left": QA_MAX_REPAIRS, 
            "intent": intent,
            "chart_intent" : CHART_INTENT_ALIASES.get(intent, intent)
        }
    

    def run_sql(self, state: dict, query: str) -> dict:
        """Execute query"""
        print(f"traffic_agent :: run_sql :: state :: {state}")
        query = state["sql_query"]
        _lquery = query.lower().lstrip()
        if query == "NOT_RELEVANT":
            return {"sql_valid": False}
        
        if not (_lquery.startswith("select") or _lquery.startswith("with")):
            return {
                "sql_valid": False,
                "sql_issues": "Only read-only SELECT/WITH queries are allowed."
            }
        
        try:
            result = self.db_manager.execute_query(uuid=state['request_id'], 
                                                   query=query)
            return {
                "sql_valid": True, 
                "results": result["rows"],
                "row_count": result["rowCount"],
                "columns": result["columns"]
                }
        except Exception as e:
            return {"error": str(e)}
    