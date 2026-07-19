from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_ollama import ChatOllama
from langchain_core.tools import ToolException
from langgraph.checkpoint.memory import InMemorySaver

from langchain_core.callbacks import FileCallbackHandler
from langchain_core.callbacks.base import BaseCallbackHandler

import asyncio
#import nest_asyncio
#nest_asyncio.apply()

from typing import Literal
from langchain.tools import tool

import os


class DerivedCallbackHandler(BaseCallbackHandler):
    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id = None, tags = None, metadata = None, **kwargs):
        print(f"On chain start :: serialized :: {serialized}\n :: inputs :: {inputs}\n :: tags :: {tags}\n :: run_id :: {run_id}\n ")

    def on_chain_end(self, outputs, *, run_id, parent_run_id = None, **kwargs):
        print(f"On chain end :: outputs :: {outputs}\n :: run_id :: {run_id}\n ")

    def on_chain_error(self, error, *, run_id, parent_run_id = None, **kwargs):
        print(f"On chain end :: error :: {error}\n :: run_id :: {run_id}\n ")

    def on_llm_start(self, serialized, prompts, *, run_id, parent_run_id = None, tags = None, metadata = None, **kwargs):
        print(f"On LLM start :: serialized :: {serialized}\n :: prompts :: {prompts}\n :: tags :: {tags}\n :: run_id :: {run_id}\n ")

    def on_llm_new_token(self, token, *, chunk = None, run_id, parent_run_id = None, tags = None, **kwargs):
        print(f"On LLM new token :: token :: {token}\n :: tags :: {tags}\n :: run_id :: {run_id}\n ")
    
    def on_llm_end(self, response, *, run_id, parent_run_id = None, tags = None, **kwargs):
        print(f"On LLM end :: response :: {response}\n :: tags :: {tags}\n :: run_id :: {run_id}\n ")
    
    def on_llm_error(self, error, *, run_id, parent_run_id = None, tags = None, **kwargs):
        print(f"On LLM error :: error :: {error}\n :: tags :: {tags}\n :: run_id :: {run_id}\n ")
      
    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id = None, tags = None, metadata = None, **kwargs):
        print(f"On Chat Model start :: serialized :: {serialized}\n :: messages :: {messages}\n :: tags :: {tags}\n :: run_id :: {run_id}\n ")

    def on_agent_action(self, action, *, run_id, parent_run_id = None, **kwargs):
        print(f"On agent action :: action :: {action}\n :: run_id :: {run_id}\n ")

    def on_agent_finish(self, finish, *, run_id, parent_run_id = None, **kwargs):
        print(f"On agent action :: finish :: {finish}\n :: run_id :: {run_id}\n ")

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id = None, tags = None, metadata = None, inputs = None, **kwargs):
        print(f"On tool start :: serialized :: {serialized}\n :: input_str :: {input_str}\n :: tags :: {tags}\n :: run_id :: {run_id}\n ")

    def on_tool_end(self, output, *, run_id, parent_run_id = None, **kwargs):
        print(f"On tool start :: output :: {output}\n :: run_id :: {run_id}\n ")

    def on_tool_error(self, error, *, run_id, parent_run_id = None, **kwargs):
        print(f"On tool start :: error :: {error}\n :: run_id :: {run_id}\n ")
        
    def on_text(self, text, *, run_id, parent_run_id = None, **kwargs):
        print(f"On text :: text :: {text}\n :: run_id :: {run_id}\n ")



def get_system_prompt():
    return """
### Instructions:
Your task is to convert a question into a MySQL query, given a MySQL database schema.
Adhere to these rules:
- **Deliberately go through the question and database schema word by word** to appropriately answer the question
- **Use Table Aliases** to prevent ambiguity. For example, `SELECT table1.col1, table2.col1 FROM table1 JOIN table2 ON table1.id = table2.id`.
- When creating a ratio, always cast the numerator as float

### Input:
Generate a MySQL query that answers the question.
This query will run on a database whose schema is represented in this string:
CREATE TABLE NODE_TBL ( 

  NodeNumber SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT, -- Unique ID for each network node 

  NodeID VARCHAR(15) NOT NULL, -- Router IP Address 

  NodeName VARCHAR(128) DEFAULT NULL, -- Router hostname 

  LocalAsNumber INT DEFAULT NULL, -- Autonomous System Number 

  NodeDesc VARCHAR(256) DEFAULT NULL, -- Router version/model description 

  VendorName VARCHAR(20) DEFAULT NULL, -- Vendor name (Cisco, Juniper, Nokia, etc.) 

  NodeType ENUM('router','switch') DEFAULT NULL, -- Device category 

  RouterType ENUM('P','PE','CPE') DEFAULT NULL, -- MPLS router role 

  Status SMALLINT UNSIGNED DEFAULT '2', -- Internal status flag 

  isUpdated SMALLINT UNSIGNED DEFAULT '2', -- Discovery synchronization status 

  PRIMARY KEY (NodeNumber), 

  UNIQUE KEY NodeID (NodeID) 

); 

 

CREATE TABLE NODEIF_TBL ( 

  IfID INT UNSIGNED NOT NULL AUTO_INCREMENT, -- Unique ID for each interface 

  NodeNumber SMALLINT UNSIGNED DEFAULT NULL, -- Node reference from NODE_TBL 

  IfIndex INT UNSIGNED DEFAULT NULL, -- Logical interface index 

  IfIndexPhy INT UNSIGNED DEFAULT NULL, -- Physical interface index 

  IfDescr VARCHAR(128) DEFAULT NULL, -- Interface name 

  IfType ENUM(...) DEFAULT NULL, -- Interface type (Ethernet, MPLS, PPP, Tunnel, etc.) 

  IfAdminStatus ENUM('up','down','testing') DEFAULT NULL, -- Administrative status 

  IfOperStatus ENUM( 

    'up','down','testing','unknown', 

    'dormant','notpresent','lowerLayerDown' 

  ) DEFAULT NULL, -- Interface Operational status 

  IfMtu SMALLINT UNSIGNED DEFAULT NULL, -- Maximum Transfer Unit 

  IfSpeed BIGINT UNSIGNED DEFAULT NULL, -- Configured bandwidth 

  IfIPAddress VARCHAR(16) DEFAULT NULL, -- Interface IP Address 

  IfDuplexStatus ENUM( 

    'unknown','halfDuplex','fullDuplex' 

  ) DEFAULT NULL, -- Duplex communication mode 

  IfPhyAddress VARCHAR(18) DEFAULT NULL, -- Physical MAC address 

  IfLastChange VARCHAR(64) DEFAULT NULL, -- Last interface status change 

  IfAlias VARCHAR(600) DEFAULT NULL, -- Interface Description 

  CreateTime TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00', -- Interface creation timestamp 

  UpdateTime TIMESTAMP NOT NULL DEFAULT '0000-00-00 00:00:00', -- Last polling/discovery update 

  IfActive VARCHAR(2) DEFAULT 'Y', -- Indicates whether interface is active 

  PRIMARY KEY (IfID), 

  UNIQUE KEY idx_nn_desc (NodeNumber, IfDescr) 

); 

 

CREATE TABLE VLANPRT_TBL ( 

  PrtID BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, -- Unique ID for each interface 

  NodeID SMALLINT DEFAULT NULL, -- Node reference from NODE_TBL 

  PrtStatus SMALLINT DEFAULT NULL, -- Port status indicator 

  VlanId SMALLINT DEFAULT NULL, -- VLAN Identifier 

  IfIndex INT DEFAULT NULL, -- Logical interface index 

  Status SMALLINT UNSIGNED DEFAULT '2', -- Internal polling status 

  Class VARCHAR(4) DEFAULT NULL, -- Polling eligibility flag 

  counterType INT DEFAULT '64', -- Counter type used for polling 

  IfDescr VARCHAR(128) DEFAULT NULL, -- Interface name 

  IfID INT UNSIGNED DEFAULT '0', -- Interface reference from NODEIF_TBL 

  PRIMARY KEY (PrtID) 

); 

 

CREATE TABLE ROUTERTRAFFIC_VLANPRT_SCALE1_TBL_B ( 

  PortID BIGINT UNSIGNED NOT NULL DEFAULT '0', -- VLAN Port ID reference 

  TxOctets BIGINT UNSIGNED DEFAULT NULL, -- Outgoing traffic statistics 

  RcvOctets BIGINT UNSIGNED DEFAULT NULL, -- Incoming traffic statistics 

  InDiscPkts BIGINT UNSIGNED DEFAULT NULL, -- Incoming discarded packets 

  InErrPkts BIGINT UNSIGNED DEFAULT NULL, -- Incoming error packets 

  OutDiscPkts BIGINT UNSIGNED DEFAULT NULL, -- Outgoing discarded packets 

  OutErrPkts BIGINT UNSIGNED DEFAULT NULL, -- Outgoing transmission errors 

  Time_1 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP 

    ON UPDATE CURRENT_TIMESTAMP, -- Polling timestamp 

  CrcAlignErr BIGINT DEFAULT NULL, -- CRC alignment errors 

  PRIMARY KEY (PortID, Time_1) 

); 

 

CREATE TABLE NODEANDIF_STATIC_TBL ( 

  ACircle VARCHAR(50) DEFAULT NULL, -- A-End circle 

  ZCircle VARCHAR(50) DEFAULT NULL, -- Z-End circle 

  ATier VARCHAR(2) DEFAULT NULL, -- A-End tier 

  ZTier VARCHAR(2) DEFAULT NULL, -- Z-End tier 

  ACity VARCHAR(40) DEFAULT NULL, -- A-End city 

  ZCity VARCHAR(40) DEFAULT NULL, -- Z-End city 

  AM6code VARCHAR(100) DEFAULT NULL, -- A-End M6 code 

  ZM6code VARCHAR(100) DEFAULT NULL, -- Z-End M6 code 

  VendorName VARCHAR(20) DEFAULT NULL, -- Vendor name 

  ANodeNumber SMALLINT UNSIGNED DEFAULT NULL, -- A-End node reference 

  ANodeID VARCHAR(15) NOT NULL, -- A-End Router IP 

  ANodeName VARCHAR(128) DEFAULT NULL, -- A-End Router name 

  AIfID INT UNSIGNED DEFAULT NULL, -- A-End Interface ID 

  AIfDescr VARCHAR(128) DEFAULT NULL, -- A-End Interface description 

  APortID BIGINT UNSIGNED DEFAULT NULL, -- A-End VLAN Port ID 

  ZNodeNumber SMALLINT UNSIGNED DEFAULT NULL, -- Z-End node reference 

  ZNodeID VARCHAR(15) NOT NULL, -- Z-End Router IP 

  ZNodeName VARCHAR(128) DEFAULT NULL, -- Z-End Router name 

  ZIfID INT UNSIGNED DEFAULT NULL, -- Z-End Interface ID 

  ZIfDescr VARCHAR(128) DEFAULT NULL, -- Z-End Interface description 

  ZPortID BIGINT UNSIGNED DEFAULT NULL, -- Z-End VLAN Port ID 

  IfAdminStatus ENUM('up','down','testing') DEFAULT NULL, -- Administrative interface state 

  IfOperStatus ENUM( 

    'up','down','testing','unknown', 

    'dormant','notpresent','lowerLayerDown' 

  ) DEFAULT NULL, -- Operational interface state 

  Class VARCHAR(4) DEFAULT NULL, -- Polling classification 

  IfSpeed BIGINT UNSIGNED DEFAULT NULL, -- Configured interface bandwith 

  LinkType VARCHAR(100) DEFAULT NULL, -- Link category/type 

  LinkSubType VARCHAR(30) DEFAULT NULL, -- Link sub-category 

  RingName VARCHAR(100) DEFAULT NULL, -- Ring topology name 

  ParentIfID INT UNSIGNED DEFAULT NULL, -- Parent interface ID 

  ParentIfDescr VARCHAR(128) DEFAULT NULL, -- Parent interface name 

  Flag VARCHAR(20) DEFAULT NULL, -- Interface classification 

  IfAlias VARCHAR(1024) DEFAULT NULL, -- Interface Description 

  AIfIndex INT UNSIGNED DEFAULT NULL -- Logical interface index 

); 

 

-- NODEIF_TBL.NodeNumber can be joined with NODE_TBL.NodeNumber 

-- VLANPRT_TBL.NodeID can be joined with NODE_TBL.NodeNumber 

-- VLANPRT_TBL.IfID can be joined with NODEIF_TBL.IfID 

-- ROUTERTRAFFIC_VLANPRT_SCALE1_TBL_B.PortID can be joined with VLANPRT_TBL.PrtID 

-- NODEANDIF_STATIC_TBL.ANodeNumber can be joined with NODE_TBL.NodeNumber 

-- NODEANDIF_STATIC_TBL.ZNodeNumber can be joined with NODE_TBL.NodeNumber 

-- NODEANDIF_STATIC_TBL.AIfID can be joined with NODEIF_TBL.IfID 

-- NODEANDIF_STATIC_TBL.ZIfID can be joined with NODEIF_TBL.IfID 

-- NODEANDIF_STATIC_TBL.APortID can be joined with VLANPRT_TBL.PrtID 

-- NODEANDIF_STATIC_TBL.ZPortID can be joined with VLANPRT_TBL.PrtID 

### Response:
Based on your instructions, here is the SQL query I have generated to answer the question:
```sql
"""

async def main():

    o_model = ChatOllama(model="llama3.2:3b")

    mcp_client = MultiServerMCPClient(
        {
            "database": {
                "transport": "http",  # HTTP-based remote server
                # Ensure you start your weather server on port 8000
                "url": "http://127.0.0.1:8080/mcp",
            }
        }
    )

    # Get tools
    tools = await mcp_client.get_tools()
    print([f"{o.name} : {o.description}\n" for o in tools])
    # agent = create_agent("ollama:llama3.2", tools)
    agent = create_agent(
            o_model, 
            tools, 
            checkpointer=InMemorySaver(),
            #system_prompt=get_system_prompt()
            )   

    while True:
        question = input("Please enter your question here (Type 'quit' to exit):")
        if question.strip().lower() == "quit":
            break
        print(f"Q: {question}\n")
        input_content = [
            {"user":"system", "content": get_system_prompt()},
            {"user":"user", "content": question},
        ]
        # math_response = await agent.ainvoke({"messages": "list tables in Vegayan_BRAS database"})
        try:
            async for step in agent.astream({"messages" : question},
                                            {"configurable": {"thread_id": "1"}},
                                            stream_mode="values"):
                # print(step)
                step["messages"][-1].pretty_print()
        except ToolException as e:
            print(f"Tool failed: {e}")

        print("\n" *3)
        # math_response = await o_model.bind_tools(tools).ainvoke("list tables in Vegayan_BRAS database")
        # print(math_response)

    print("Hello from mcp-demo-lcg!")


if __name__ == "__main__":
    asyncio.run(main())