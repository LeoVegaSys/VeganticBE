#!/usr/bin/env python3

### MCP CONFIG
MCP_DB_URL="http://127.0.0.1:8080/mcp"
# MCP_CONFIG= {
#             # "time": {
#             #     "transport": "stdio",
#             #     "command": "npx",
#             #     "args": ["-y", "@theo.foobar/mcp-time"],
#             # },
#             "duckdb": {
#                 "command": "uvx",
#                 "args": ["mcp-server-motherduck", "--db-path", "./data/duckdb/traffic.db", "--readonly"],
#                 "transport": "stdio"
#             },
#             "mysql": {
#                 "transport": "http",  # HTTP-based remote server
#                 # Ensure you start your weather server on port 8000
#                 "url": "http://127.0.0.1:8080/mcp",
#             }
#         }

MCP_CONFIG={
    "mysql":{
        "server":{
                "transport": "http",  # HTTP-based remote server
                # Ensure you start your weather server on port 8000
                "url": "http://127.0.0.1:8080/mcp",
            },
        "query_function": "run_query",
        "query_key": "query",
    },
    "duckdb":{
        "server": {
                "command": "uvx",
                "args": ["mcp-server-motherduck", "--db-path", "./data/duckdb/traffic.db"],
                "transport": "stdio"
            },
        "query_function": "execute_query",
        "query_key": "sql",
    },
}


### LLM CONFIG
PARSE_QUESTION_LLM="lllama3.2"
GET_UNIQUE_NOUNS_LLM="llama3.2"
GENERATE_SQL_LLM="llama3.2"
VALIDATE_AND_FIX_SQL_LLM="llama3.2"
EXECUTE_SQL_LLM="llama3.2"
FORMAT_RESULTS_LLM="llama3.2"
CHOOSE_VISUALIZATION_LLM="llama3.2"
FORMAT_DATA_FOR_VISUALIZATION_LLM="llama3.2"

STEP_LLMS={
    "parse_question" : "llama3.2",
    "get_unique_nouns" : "llama3.2",
    "generate_sql" : "llama3.2",
    "validate_and_fix_sql" : "llama3.2",
    "execute_sql" : "llama3.2",
    "format_results" : "llama3.2",
    "choose_visualization" : "llama3.2",
    "format_data_for_visualization" : "llama3.2",
}