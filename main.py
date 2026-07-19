"""
This Python file is written to test the following features:
    - Sample tool functions to test features unknown to LLM. 
        Creating functions for made-up functionality to check 
        for model hallucinations and control. 
    - Test performance of multiple models ranging in parameters
        from 250m to 8b.
    - Test langgraph swarm feature that internally allows handoffs
        to constituent agents
        Test handoffs between simple agents for simple user queries
        to induce agemts handoffs based on capabilities
    - Test deep agents capability to handle handoffs between 
        subagents
    - Test multiple models for different agents/subagents to check 
        for model efficiency and suitability
"""

from typing import Annotated, TypedDict
from uuid import uuid4

from langchain_ollama import ChatOllama

from langchain.agents import create_agent
from langchain.tools import tool, BaseTool, InjectedToolCallId
from langchain.messages import ToolMessage, AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.graph.state import CompiledStateGraph

from langgraph_swarm import create_swarm, create_handoff_tool
from deepagents import create_deep_agent, CompiledSubAgent


_model_l2 = ChatOllama(model="llama3.2", temperature=0.0)
_model_l1 = ChatOllama(model="llama3.2:1b", temperature=0.0)
_model_qw = ChatOllama(model="qwen2.5:0.5b", temperature=0.0)
_model_fg = ChatOllama(model="functiongemma:270m", temperature=0.0)

_checkpointer = InMemorySaver()
_store = InMemoryStore()

class NewState(TypedDict):
    pass

def get_astropathy(city: str | None) -> str:
    """
    Returns astropathy details for a given city
    Args: 
        city (str) : Name of city for which astropathy is to be provided
    Returns:
        str : Astropathy response for a given city in string format
    """
    return f"{city} is experiencing thunderstorms"


def get_weather(city: str | None) -> str:
    """Gets weather details for a given city"""
    return f"{city} is experiencing thunderstorms"


def add(a: int, b: int) -> int:
    """Adds two numbers"""
    return a+b

def create_custom_handoff_tool(*, agent_name:str, name: str | None, description: str| None):

    @tool(name, description=description)
    def handoff_to_agent(
        task_description: Annotated[str, 'Detailed description of what the next agent should do, inclusive of context'],
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ):
        tool_message = ToolMessage(
            content=f"Successfully transferred to {agent_name}",
            name=name,
            tool_call_id=tool_call_id,
        )

        messages = state["messages"]
        return Command(
            goto=agent_name,
            graph=Command.PARENT,
            update={
                "messages": messages + [tool_message],
                "active_agent": agent_name,
                "task_description": task_description,
            }
        )

    return handoff_to_agent

transfer_to_agent_1=create_custom_handoff_tool(
    agent_name="agent_1",
    name="transfer_to_agent_1",
    description="Transfer to agent_1, it is an expert in astropathy",
)

transfer_to_agent_2=create_custom_handoff_tool(
    agent_name="agent_2",
    name="transfer_to_agent_2",
    description="Transfer to agent_2",
)

DEF=create_deep_agent(
    name="DEF",
    model=_model_fg,
    system_prompt="""You are DEF, an AstroPathy expert. Use get_astropathy tool to respond to astropathy queries. Respond in one sentence ONLY.
    If UVW agent is requested, transfer to UVW""",
    tools=[
        get_astropathy,
        create_handoff_tool(agent_name="UVW"),
    ]
)

UVW=create_deep_agent(
    name="UVW",
    model=_model_qw,
    system_prompt="""You are UVW. If astropathy queries are requested, transfer to DEF.""",
    tools=[
        create_handoff_tool(agent_name="DEF", description="Ask DEF for answers to astropathy queries.")
    ]
)

ABC=create_agent(
    model=_model_l2,
    tools=[
        # add,
        # get_weather,
        get_astropathy,
        # transfer_to_agent_2,
        # create_custom_handoff_tool(
        #     agent_name="agent_2",
        #     name="transfer_to_agent_2",
        #     description="Transfer to agent_2, it is good in summarization",
        # ),
        create_handoff_tool(agent_name="XYZ")
    ],
    # system_prompt="You are an addition expert",
    # system_prompt="You are ABC. You are an AstroPathy expert. Use get_astropathy tool ONLY. Transfer to XYZ for response summarization.",
    system_prompt="""You are ABC, an AstroPathy expert. Use get_astropathy tool to respond to astropathy queries. Respond in one sentence ONLY.
    If XYZ agent is requested, transfer to XYZ""",
    name="ABC",
)

XYZ=create_agent(
    model=_model_l2,
    tools=[
        # transfer_to_agent_1,
        # create_custom_handoff_tool(
        #     agent_name="agent_1",
        #     name="transfer_to_agent_1",
        #     description="Transfer to agent_1, it is an expert in astropathy",
        # ),
        create_handoff_tool(agent_name="ABC", description="Ask ABC for solution to astropathy queries.")
    ],
    system_prompt="""You are XYZ. If astropathy queries are requested, transfer to ABC.""",
    name="XYZ",
)

RST=create_deep_agent(
    name="RST",
    model=_model_qw,
    system_prompt="""You are RST, an orchestration agent to manage two sub-agents ABC and XYZ. 
    If astropathy queries are requested, transfer to ABC. For summarization, transfer to XYZ.
    """,
    subagents=[
        CompiledSubAgent(
            name = "ABC",
            description = "Specialized agent to provide answers to astropathy queries.",
            runnable=ABC,
        ), 
        CompiledSubAgent(
            name="XYZ",
            description="Specialized agent for summarization.",
            runnable=XYZ,
        ),
    ],
)

workflow = create_swarm(
    # [DEF, UVW],
    # default_active_agent="UVW",
    [ABC, XYZ],
    default_active_agent="XYZ",
)


def print_agent_invoke_messages(app:CompiledStateGraph, thread_config: dict | None, content: str | None):
    for step in app.stream(
        {
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ]
        },
        thread_config,
        stream_mode="values"
    ):
        # print(f"{step}\n")
        step["messages"][-1].pretty_print()


def main():
    print("Hello from swarm-handoffs!")

    app = workflow.compile(
        checkpointer=_checkpointer,
        store=_store
    )

    thread_config = {
        "configurable" : {
            "thread_id": str(uuid4()),
        }
    }

    """
    turn_1=app.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "I'd like to talk to Agent 2",
                }
            ]
        },
        thread_config,
    )
    print(turn_1)
    
    turn_2=app.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "What is 32 + 90?",
                }
            ]
        },
        thread_config,
    )
    print(turn_2)
    """

    while True:
        question=input("Enter your question here (Enter `quit` to exit) :")
        if question.strip().lower() == "quit":
            break
        # print_agent_invoke_messages(app, thread_config, content="I'd like to talk to Agent 2")
        # print_agent_invoke_messages(app, thread_config, content="What is 32 + 90?")
        # print_agent_invoke_messages(app, thread_config, content="What is the weather like in New York?")
        print_agent_invoke_messages(app, thread_config, content=question)
        # print_agent_invoke_messages(app, thread_config, content="Hi!")


if __name__ == "__main__":
    main()
