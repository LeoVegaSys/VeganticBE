from langgraph.graph import StateGraph, START, END

from state.traffic_state import TrafficState, TrafficOutputState
from agents.traffic_db_agent import TrafficAgent

class TrafficWorkflowManager:
    def __init__(self):
        self.sql_agent=TrafficAgent()

    def create_workflow(self) -> StateGraph:
        """Create and configure the workflow graph."""
        workflow = StateGraph(state_schema=TrafficState,
                              input_schema=TrafficState,
                              output_schema=TrafficOutputState)

        workflow.add_node("warmup", self.sql_agent.warmup)
        workflow.add_node("generate_sql", self.sql_agent.generate_sql)
        workflow.add_node("run_sql", self.sql_agent.run_sql)
        workflow.add_node("repair_sql", self.sql_agent.repair_sql)
        workflow.add_node("summarize", self.sql_agent.summarize)

        workflow.add_edge("warmup", "generate_sql")
        workflow.add_edge("generate_sql", "run_sql")
        workflow.add_edge("run_sql", "repair_sql")
        workflow.add_edge("summarize", END)

        workflow.set_entry_point("warmup")

        return workflow
    
    def returnGraph(self):
        return self.create_workflow().compile()
    
    def run_traffic_agent(self, question: str, mcp_server:str, summarize: bool, request_id: str) -> dict:
        print(f"\nTrafficGraph :: run_traffic_agent :: Q {question} :: DT {mcp_server} :: SMR {summarize} :: ID {request_id}")
        app = self.create_workflow().compile()
        result = app.invoke(
            {"question": question, "summarize": summarize, "request_id": request_id, "mcp_server":mcp_server}
        )
        print(f"\nrun_traffic_agent :: result :: {result}")
        return result
        return {
            "request_id": result["request_id"],
            "results": result['results'],
            "summary": result["summary"],
        }
