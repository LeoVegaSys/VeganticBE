from typing import List, Any, Annotated, Dict, Optional
from typing_extensions import TypedDict
import operator

class TrafficState(TypedDict):
    request_id: str
    question: str
    mcp_server: str
    sql_query: str
    sql_valid: bool
    sql_issues: str
    error: str
    row_count: int
    columns: List[str]
    results: List[Any]
    summary: Annotated[str, operator.add]
    visualization: Annotated[str, operator.add]
    visualization_reason: Annotated[str, operator.add]
    formatted_data_for_visualization: Dict[str, Any]
    intent: str
    chart_intent: str
    repairs_left: int
    summarize: bool
    