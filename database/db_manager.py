import requests
import asyncio
from typing import List, Any
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from config import DB_ENDPOINT_URL, MCP_DB_TYPE
from utils.mcp import get_mcp_details, parse_mcp_query_response


class DatabaseManager:

    def __init__(self):
        self.endpoint_url = DB_ENDPOINT_URL


    def get_schema(self, uuid: str, db_name:str) -> str:
        """Retrieve the database schema."""
        print(f"\nDBM :: schema :: DB {db_name} :: ID {uuid}")
        result=asyncio.run(_get_schema(uuid, db_name))
        return result
    

    def execute_query(self, uuid: str, query: str) -> List[Any]:
        """Execute SQL query on the remote database and return results.""" 
        print(f"\nDBM :: Q {query} :: ID {uuid} :: DT {MCP_DB_TYPE}")
        result=asyncio.run(_execute_query(uuid, query))
        return result


async def _execute_query(uuid: str, query: str, mcp_server_name: str = ""):
    """ Calls Database MCP server and returns query results"""
    try:
        mcp_server = mcp_server_name or MCP_DB_TYPE.lower()
        mcp_config, mcp_func, mcp_key = get_mcp_details()
        mcp_client = MultiServerMCPClient(mcp_config)

        async with mcp_client.session(server_name=mcp_server) as session:
        # Get tools
          # tools = await mcp_client.get_tools(server_name=mcp_server)
          tools = await load_mcp_tools(session)
          run_tool = next(t for t in tools if t.name==mcp_func[mcp_server])
          # result = await mcp_client.call_tool("run_query", query)
          result=await run_tool.ainvoke({ mcp_key[mcp_server]: query })

        print(f"\nDBM :: _execute_query :: Result: {result}")
        return parse_mcp_query_response(result)

    except Exception as e :
        err_msg = f"MCP :: Error encountered while executing {mcp_server} :: query {query} : {str(e)}"
        print(err_msg)
        raise e


async def _get_schema(uuid: str, db_name: str, mcp_server_name: str = ""):
    """ Calls Database MCP server and returns query results"""
    try:
        mcp_server = mcp_server_name or MCP_DB_TYPE.lower()
        mcp_config, mcp_func, mcp_key = get_mcp_details()
        mcp_client = MultiServerMCPClient(mcp_config)

        async with mcp_client.session(server_name=mcp_server) as session:
          schema = await session.read_resource(f"schema://{db_name}")
          result = schema.contents[0].text
        print(f"\nDBM :: _get_schema :: Result: {result}")
        return result

    except Exception as e :
        err_msg = f"MCP :: Error encountered while getting {mcp_server} :: {db_name} schema : {str(e)}"
        print(err_msg)
        raise e
