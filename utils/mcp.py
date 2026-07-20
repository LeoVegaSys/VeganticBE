import json
from typing import Union

from mcp_config import MCP_CONFIG

def get_mcp_details():
    mcp_server_config = {}
    mcp_func = {}
    mcp_key = {}
    for key, val in MCP_CONFIG.items():
        """Get MCP server details"""
        mcp_server_config[key] = val["server"]
        """Get MCP executor function details"""
        mcp_func[key] = val["query_function"]
        """Get MCP API key details"""
        mcp_key[key] = val["query_key"]
    return (mcp_server_config, mcp_func, mcp_key)

def parse_mcp_query_response(mcp_result: Union[list, dict, str, None]) -> dict:
    """
    Parse MCP Tool Query Execution response
    Input args:
        Expected mcp_result structure:
        [
            {'type': 'text',
            'text': '{
                \n  "success": true,
                \n  "columns": [\n    "LinkType",\n    "Node Name",\n    ...],
                \n  "columnTypes": [\n    "VARCHAR",\n    "VARCHAR",\n    ...],
                \n  "rows": [\n    [\n      "Core",\n      "HYD_OHR_901_...]\n  ],
                \n  "rowCount": 5\n}',
            'id': 'lc_42c9b207-fc49-4e31-a50a-c0fa18ecf9ad'}
            ]
    Output:
        {
            "success": true,
            "columns": ["NodeNumber", "NodeID", ...],
            "columnTypes": ["SHORT", "VAR_STRING", ...],
            "rows": [{"NodeNumber": 117, "NodeID": "202.123.37.241", ...}],
            "rowCount": 5
        }
    """

    try:
        return json.loads(mcp_result[0]['text'])
    except Exception as e:
        raise e