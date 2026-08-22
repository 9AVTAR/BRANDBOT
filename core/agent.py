"""
Builds a per-tenant LangGraph agent: LLM node + ToolNode, with conditional
routing (tools_condition) so the agent loops between "think" and "act" until
it has a final answer. This is the same core pattern from the
"Tools in LangGraph" lesson — bind_tools + ToolNode + tools_condition —
applied to a multi-tenant setting where each company gets its own tool set
and its own system prompt.

Persistence: SqliteSaver (from langgraph-checkpoint-sqlite) is used instead
of MemorySaver so that conversation history survives app restarts. Each
conversation is keyed by thread_id (tenant_id + session UUID), so histories
never leak across tenants or sessions.
"""

import os
import sqlite3
import streamlit as st
from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition

from core.tools import build_tenant_tools

# SQLite DB file for chat history persistence
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "checkpoints.db")
os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)

# SqliteSaver needs a raw sqlite3 connection
# One shared connection + checkpointer for all tenants;
# thread_id separates conversations so no cross-tenant leakage
_conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
_checkpointer = SqliteSaver(_conn)

_compiled_graph_cache: dict[str, object] = {}


def _get_system_prompt(company_name: str) -> str:
    return (
        f"You are the official support assistant for {company_name}. "
        "Answer using the search_company_documents tool whenever the question "
        "relates to the company, its products, policies, or services — never "
        "guess if you can look it up. If a tool isn't relevant, answer directly. "
        "If no relevant information is found anywhere, say so honestly instead "
        "of making something up. Keep answers concise and friendly."
    )


def _build_graph(tenant_id: str, company_name: str, model_name: str, custom_tool_configs: list):
    tools = build_tenant_tools(tenant_id, company_name, custom_tool_configs)

    llm = ChatGroq(
        model=model_name,
        api_key=st.secrets.get("GROQ_API_KEY", ""),
        temperature=0.3,
    ).bind_tools(tools)

    system_prompt = _get_system_prompt(company_name)

    def agent_node(state: MessagesState):
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages
        response = llm.invoke(messages)
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=_checkpointer)


def get_agent(tenant_id: str, company_name: str, model_name: str, custom_tool_configs: list, force_rebuild: bool = False):
    """Cached per-tenant graph so we don't rebuild it on every Streamlit rerun.
    force_rebuild=True is used after the admin adds a new custom tool, so the
    agent picks it up immediately."""
    cache_key = f"{tenant_id}:{model_name}:{len(custom_tool_configs)}"
    if force_rebuild or cache_key not in _compiled_graph_cache:
        _compiled_graph_cache[cache_key] = _build_graph(
            tenant_id, company_name, model_name, custom_tool_configs
        )
    return _compiled_graph_cache[cache_key]
