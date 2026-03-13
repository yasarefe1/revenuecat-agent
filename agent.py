"""
agent.py — LangGraph ReAct Agent Orchestration
Wraps every module function as a LangGraph tool and runs
them through a ReAct-style reasoning loop.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Annotated, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel

from modules import decision_logger
from modules import revenuecat_client
from modules import content_engine
from modules import community_engine
from modules import reporting
from modules import publisher

# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class AgentState(BaseModel):
    """State carried through the LangGraph execution."""
    messages: Annotated[list, add_messages] = []
    current_task: str = ""
    results: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Tools — one per module capability
# ---------------------------------------------------------------------------

@tool
async def plan_content_week() -> str:
    """Plan the next week of content — selects the next 2 titles from the calendar."""
    result = await content_engine.plan_week()
    return json.dumps(result)


@tool
async def produce_content() -> str:
    """Produce the next blog post from the content calendar using Gemini."""
    result = await content_engine.produce_and_publish()
    return json.dumps(result, default=str)


@tool
def get_content_history() -> str:
    """Retrieve all content items (pending + published) from the database."""
    result = content_engine.get_history()
    return json.dumps(result, default=str)


@tool
async def scan_community() -> str:
    """Scan RevenueCat GitHub repos for unanswered issues and draft replies."""
    result = await community_engine.scan_and_engage()
    return json.dumps(result)


@tool
def get_community_stats() -> str:
    """Get community interaction counts (this week + total)."""
    result = community_engine.get_interaction_count()
    return json.dumps(result)


@tool
async def explore_revenuecat_api() -> str:
    """Explore RevenueCat API endpoints and generate feature requests."""
    result = await revenuecat_client.explore_and_document()
    return json.dumps(result)


@tool
async def generate_weekly_report() -> str:
    """Generate the weekly performance report."""
    result = await reporting.generate_and_send()
    return result  # Already markdown string


@tool
async def get_latest_report() -> str:
    """Retrieve the most recently generated weekly report."""
    result = await reporting.get_latest()
    return result or "No reports generated yet."


@tool
def get_decision_log() -> str:
    """Retrieve ALL agent decisions with full reasoning."""
    result = decision_logger.get_all_decisions()
    return json.dumps(result, default=str)


@tool
def get_weekly_decisions() -> str:
    """Retrieve agent decisions from the last 7 days."""
    result = decision_logger.get_decisions_this_week()
    return json.dumps(result, default=str)


@tool
async def publish_to_gist(title: str, content: str) -> str:
    """Publish approved content to a public GitHub Gist. Requires operator approval."""
    try:
        url = await publisher.publish_gist(title, content, operator_approved=True)
        return f"Published: {url}"
    except PermissionError as e:
        return f"BLOCKED: {str(e)}"


# ---------------------------------------------------------------------------
# All tools
# ---------------------------------------------------------------------------
ALL_TOOLS = [
    plan_content_week,
    produce_content,
    get_content_history,
    scan_community,
    get_community_stats,
    explore_revenuecat_api,
    generate_weekly_report,
    get_latest_report,
    get_decision_log,
    get_weekly_decisions,
    publish_to_gist,
]

# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_agent_graph() -> StateGraph:
    """
    Build a LangGraph StateGraph with the ReAct pattern:
      agent (reason) → tools (act) → agent → ... → END
    """
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        max_output_tokens=4096,
        api_key=os.getenv("GEMINI_API_KEY", "")
    )
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    def agent_node(state: AgentState) -> dict:
        """The reasoning node — calls the LLM with tool bindings."""
        response = llm_with_tools.invoke(state.messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        """Route: if the last message has tool_calls, go to tools; else END."""
        last_message = state.messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    # Build graph
    tool_node = ToolNode(ALL_TOOLS)

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph


# Compiled graph (singleton)
_compiled_graph = None


def get_agent():
    """Get or create the compiled agent graph."""
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_agent_graph()
        _compiled_graph = graph.compile()
    return _compiled_graph


async def run_agent(task: str) -> dict:
    """
    Run the agent with a given task description.

    Args:
        task: Natural language description of what the agent should do.

    Returns:
        The final agent state as a dict.
    """
    agent = get_agent()

    decision_logger.log_decision(
        module="agent",
        action="run_agent",
        reasoning=f"Received task: '{task}'. Starting ReAct loop with LangGraph.",
        outcome="Agent execution started.",
    )

    initial_state = AgentState(
        messages=[HumanMessage(content=task)],
        current_task=task,
    )

    try:
        result = await agent.ainvoke(initial_state)

        decision_logger.log_decision(
            module="agent",
            action="run_agent_complete",
            reasoning=f"Completed task: '{task}'.",
            outcome=f"Agent finished with {len(result.get('messages', []))} messages.",
        )

        return result

    except Exception as exc:
        decision_logger.log_decision(
            module="agent",
            action="run_agent_failed",
            reasoning=f"Agent task '{task}' encountered an error.",
            outcome=f"Error: {str(exc)[:300]}",
        )
        raise
