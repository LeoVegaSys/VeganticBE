from typing import List, Any, Annotated, Dict, Optional
from typing_extensions import TypedDict
import operator

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages

class InputState(TypedDict):
    uuid: str
    messages : Annotated[list[AnyMessage], add_messages]
    question: str
    mcp_server: str
    parsed_question: Dict[str, Any]
    unique_nouns: List[str]
    sql_query: str
    results: List[Any]
    visualization: Annotated[str, operator.add]
    summarize: bool
    row_count: int
    columns: List[str]
    sql_valid: bool
    sql_issues: str
    error: str

class OutputState(TypedDict):
    uuid: str
    # messages : Annotated[list[AnyMessage], add_messages]
    parsed_question: Dict[str, Any]
    unique_nouns: List[str]
    sql_query: str
    sql_valid: bool
    sql_issues: str
    results: List[Any]
    summary: Annotated[str, operator.add]
    error: str
    visualization: Annotated[str, operator.add]
    visualization_reason: Annotated[str, operator.add]
    formatted_data_for_visualization: Dict[str, Any]
    intent: str
    chart_intent: str
    row_count: int
    columns: List[str]
