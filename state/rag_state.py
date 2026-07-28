from typing import List, Any, Annotated, Dict, Optional
from typing_extensions import TypedDict
import operator

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

class RagInputState(TypedDict):
    request_id: str
    messages : Annotated[list[AnyMessage], add_messages]
    question: str
    mcp_server: str
    parsed_question: Dict[str, Any]
    unique_nouns: List[str]
    results: List[Any]
    row_count: int
    columns: List[str]
    error: str
    knowledge_chunks : Annotated[List[str], operator.add]
    feedback_chunks : Annotated[List[str], operator.add]

class RagOutputState(TypedDict):
    request_id: str
    # messages : Annotated[list[AnyMessage], add_messages]
    parsed_question: Dict[str, Any]
    unique_nouns: List[str]
    results: List[Any]
    summary: Annotated[str, operator.add]
    error: str
    row_count: int
    columns: List[str]
    knowledge_chunks : Annotated[List[str], operator.add]
    feedback_chunks : Annotated[List[str], operator.add]
