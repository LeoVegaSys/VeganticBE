import json
from uuid import uuid4


from langgraph.graph import END, START
from langgraph.graph import StateGraph
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.redis import RedisSaver
from langgraph.store.redis import RedisStore
from langgraph.runtime import Runtime
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

from state.state import InputState, OutputState
from agents.sql_agent import SQLAgent
from agents.dip_agent import DipAgent
from graph.traffic_graph_manager import TrafficWorkflowManager
from data_formatter import DataFormatter
from utils.context import Context
from utils.store import write_entry_to_store, read_from_store, get_store_config, manage_store

from config import REDIS_HOST, REDIS_PORT, HISTORY


## Sub-graph routing paramters
DIP_KEYWORDS = ("dip", "dips", "dipped", "drop", "dropped", "surge", "spike",
                "sudden", "fell", "fall", "plunge", "plunged")
##

# Sub-graph router
def get_query_type(state: dict, runtime: Runtime[Context]) -> str:
    print(f"\nget_query_type :: state :: {state}")

    is_approved = interrupt("Do you want to proceed with this action?")

    try:
        manage_store(user_id=runtime.context.user_id)
        
        memories = read_from_store(
            user_id=runtime.context.user_id, category=HISTORY, 
            params=["question", "answer"]
        )
        if memories:
            memory = "\n".join([f"\n{k.upper()}:{v}" for m in memories for k,v in m.items()])
            print(f"NS :: {'memories', runtime.context.user_id} :: MemLen :: {len(memories)} :: Memory : {memory}")

        write_entry_to_store(
            user_id=runtime.context.user_id, category=HISTORY,
            param="question", data=json.dumps(state["question"])
        )
    except Exception as e:
        print(f"Error occurred during store read/write : {str(e)}")

    query = state['question'].lower()
    if any(w in query for w in DIP_KEYWORDS):
        return "calculate_dip"
    else:
        return "analyze_traffic"
    return "parse_question"


def call_traffic_graph(state: InputState, runtime: Runtime[Context]):
    print(f"\ncall_traffic_graph :: state :: {state}")
    result = TrafficWorkflowManager().run_traffic_agent(
        question=state["question"], summarize=state["summarize"], 
        request_id=state["uuid"], mcp_server=state["mcp_server"])
    
    write_entry_to_store(
        user_id=runtime.context.user_id, category="memories",
        param="answer", data=json.dumps(result)
    )
    print(f"\ntrafficGraph :: call_traffic_graph :: result :: {result}")
    return result


class WorkflowManager:
    def __init__(self):
        self.sql_agent = SQLAgent()
        self.data_formatter = DataFormatter()
        self.dip_agent = DipAgent()

    def create_workflow(self) -> StateGraph:
        """Create and configure the workflow graph."""
        workflow = StateGraph(state_schema=InputState, input=InputState, output=OutputState)

        # Add nodes from the Traffic graph
        workflow.add_node("analyze_traffic", call_traffic_graph)

        # Deterministic non-LLM-using
        workflow.add_node("calculate_dip", self.dip_agent.dip_detect)
        workflow.add_node("summarize_dip", self.dip_agent.summarize)

        # LLM-using
        workflow.add_node("parse_question", self.sql_agent.parse_question)
        workflow.add_node("get_unique_nouns", self.sql_agent.get_unique_nouns)
        workflow.add_node("generate_sql", self.sql_agent.generate_sql)
        workflow.add_node("validate_and_fix_sql", self.sql_agent.validate_and_fix_sql)
        workflow.add_node("execute_sql", self.sql_agent.execute_sql)
        workflow.add_node("format_results", self.sql_agent.format_results)
        workflow.add_node("choose_visualization", self.sql_agent.choose_visualization)
        workflow.add_node("format_data_for_visualization", self.data_formatter.format_data_for_visualization)
        
        # Define edges
        workflow.add_conditional_edges(START, get_query_type)

        workflow.add_edge("calculate_dip", "summarize_dip")
        workflow.add_edge("summarize_dip", END)

        workflow.add_edge("parse_question", "get_unique_nouns")
        workflow.add_edge("get_unique_nouns", "generate_sql")
        workflow.add_edge("generate_sql", "validate_and_fix_sql")
        workflow.add_edge("validate_and_fix_sql", "execute_sql")
        workflow.add_edge("execute_sql", "format_results")
        workflow.add_edge("execute_sql", "choose_visualization")
        workflow.add_edge("choose_visualization", "format_data_for_visualization")
        workflow.add_edge("format_data_for_visualization", END)
        workflow.add_edge("format_results", END)

        # workflow.set_entry_point("categorize")

        return workflow
    
    def returnGraph(self):
        return self.create_workflow().compile()

    def run_sql_agent(
            self, 
            db_type:str, 
            question: str = "",
            user_response: str = "",
            summarize: bool = False, 
            uuid: str = "",
            session_id: str = "SESS1",
            user_id: str = "USER1"
        ) -> dict:
        """
        Run the SQL agent workflow and return the formatted answer and visualization recommendation.
        """
        print(f"\nGraph :: run_sql_agent :: Q {question} :: DT {db_type} :: SMR {summarize} \
              :: ID {uuid} :: SID :: {session_id} :: UID :: {user_id}")

        store_uri = f"redis://{REDIS_HOST}:{REDIS_PORT}"
        checkpointer = InMemorySaver()
        with RedisStore.from_conn_string(store_uri, ttl=get_store_config()) as store:
        # checkpointer = RedisSaver.from_conn_string(store_uri)

            # app = self.create_workflow().compile(store=store)
            app = self.create_workflow().compile(store=store, checkpointer=checkpointer)
            # app = self.create_workflow().compile()

            _uuid = uuid or uuid4().hex[:12]
            config: RunnableConfig = {"configurable": {"thread_id": session_id}} if session_id else None
            context = Context(user_id=user_id) if user_id else None

            if user_response:
                result = app.invoke(Command(resume=user_response), config=config, context=context)
            else:
                result =  app.invoke(
                    input={"question": question, "uuid": _uuid, "summarize": summarize, "mcp_server": db_type},
                    config=config,
                    context=context,
                )

            snapshot = app.get_state(config)
            if snapshot.interrupts:
                result["user_input_required"] = snapshot.interrupts[0].value

            print(f"\ngraph :: run_sql_agent :: result :: {result}")
            return result
        # return {
        #     "summary": result['summary'],
        #     "visualization": result['visualization'],
        #     "visualization_reason": result['visualization_reason'],
        #     "formatted_data_for_visualization": result['formatted_data_for_visualization']
        # }
