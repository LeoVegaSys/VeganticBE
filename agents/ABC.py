from typing_extensions import TypedDict, Annotated

from langchain.messages import AnyMessage
from langgraph.graph import StateGraph, add_messages
from langgraph_swarm import SwarmState

class ABCState(TypedDict):
    abc_messages = Annotated[list[AnyMessage], add_messages]


abc = (
    StateGraph(ABCState)
    .add_node
)