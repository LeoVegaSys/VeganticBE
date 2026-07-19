import uuid
from langgraph.graph import StateGraph
from state.state import InputState, OutputState
from agents.sql_agent import SQLAgent
from agents.dip_agent import DipAgent
from graph.traffic_graph_manager import TrafficWorkflowManager
# from utils.category_router import get_query_type
from data_formatter import DataFormatter
from langgraph.graph import END, START


## Sub-graph routing paramters
DIP_KEYWORDS = ("dip", "dips", "dipped", "drop", "dropped", "surge", "spike",
                "sudden", "fell", "fall", "plunge", "plunged")
##

# Sub-graph router
def get_query_type(state: dict) -> str:
    query = state['question'].lower()
    if any(w in query for w in DIP_KEYWORDS):
        return "calculate_dip"
    else:
        return "analyze_traffic"
    return "parse_question"


def call_traffic_graph(state: InputState):
    return TrafficWorkflowManager().run_traffic_agent(
        question=state["question"], summarize=state["summarize"], 
        request_id=state["uuid"], mcp_server=state["mcp_server"])


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

    def run_sql_agent(self, question: str, db_type:str, summarize: bool = False, uuid: str = "") -> dict:
        """Run the SQL agent workflow and return the formatted answer and visualization recommendation."""
        app = self.create_workflow().compile()
        _uuid = uuid if uuid else uuid.uuid4().hex[:12]
        return app.invoke({"question": question, "uuid": _uuid, "summarize": summarize, "mcp_server": db_type})
        # return {
        #     "answer": result['answer'],
        #     "visualization": result['visualization'],
        #     "visualization_reason": result['visualization_reason'],
        #     "formatted_data_for_visualization": result['formatted_data_for_visualization']
        # }