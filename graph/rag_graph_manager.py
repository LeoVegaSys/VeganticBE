from langgraph.graph import StateGraph, START, END

from state.rag_state import RagInputState, RagOutputState
from agents.rag_agent import RAGAgent

class RAGWorkflowManager:
    def __init__(self):
        self.rag_agent=RAGAgent()

    def create_workflow(self) -> StateGraph:
        """Create and configure the workflow graph."""
        workflow = StateGraph(state_schema=RagInputState,
                              input_schema=RagInputState,
                              output_schema=RagOutputState)

        workflow.add_node("warmup", self.rag_agent.warmup)
        workflow.add_node("generate_sql", self.rag_agent.generate_sql)
        workflow.add_node("run_sql", self.rag_agent.run_sql)
        workflow.add_node("repair_sql", self.rag_agent.repair_sql)
        workflow.add_node("summarize", self.rag_agent.summarize)

        workflow.add_edge("warmup", "generate_sql")
        workflow.add_edge("generate_sql", "run_sql")
        workflow.add_edge("run_sql", "repair_sql")
        workflow.add_edge("summarize", END)

        workflow.set_entry_point("warmup")

        return workflow
    
    def returnGraph(self):
        return self.create_workflow().compile()
    
    def run_rag_agent(self, question: str, mcp_server:str, summarize: bool, request_id: str) -> dict:
        print(f"\nRAGGraph :: run_rag_agent :: Q {question} :: DT {mcp_server} :: SMR {summarize} :: ID {request_id}")
        app = self.create_workflow().compile()
        result = app.invoke(
            {"question": question, "summarize": summarize, "request_id": request_id, "mcp_server":mcp_server}
        )
        print(f"\run_rag_agent :: result :: {result}")
        return result
        return {
            "request_id": result["request_id"],
            "results": result['results'],
            "summary": result["summary"],
        }
