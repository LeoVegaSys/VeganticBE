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

    def get_schema(self, uuid: str) -> str:
        """Retrieve the database schema."""
        return _get_schema(uuid)
        try:
            response = requests.get(
                f"{self.endpoint_url}/get-schema/{uuid}"
            )
            response.raise_for_status()
            return response.json()['schema']
        except requests.RequestException as e:
            raise Exception(f"Error fetching schema: {str(e)}")

    def execute_query(self, uuid: str, query: str) -> List[Any]:
        """Execute SQL query on the remote database and return results.""" 
        print(f"DBM :: Q {query} :: ID {uuid} :: DT {MCP_DB_TYPE}")
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

        print(f"DBM :: _execute_query :: Result: {result}")
        return parse_mcp_query_response(result)

    except Exception as e :
        err_msg = f"Error encountered while executing query {query} : {str(e)}"
        print(err_msg)
        raise e


def _get_schema(uuid: str) -> str:
    return """
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

  ) DEFAULT NULL, -- Operational status 

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
"""
