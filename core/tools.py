"""
Tool factories.

1. make_retrieval_tool(tenant_id) -> a @tool bound to that tenant's private
   document collection. The LLM decides when to call it.
2. make_custom_tool(tool_config) -> turns an admin-configured "custom tool"
   (name + description + API url) into a real callable LangChain tool at
   runtime. This is how a non-technical company admin can give their bot
   new abilities (check order status, check stock, etc.) without writing code.
"""

import requests
from langchain_core.tools import StructuredTool

from core.ingestion import retrieve


def make_retrieval_tool(tenant_id: str, company_name: str) -> StructuredTool:
    def _run(query: str) -> str:
        return retrieve(tenant_id, query)

    return StructuredTool.from_function(
        func=_run,
        name="search_company_documents",
        description=(
            f"Search {company_name}'s knowledge base (uploaded docs, FAQs, product info) "
            "for information relevant to the user's question. Always use this before "
            "answering questions about the company, its products, or policies."
        ),
    )


def make_custom_tool(tool_config: dict) -> StructuredTool:
    """Builds a runtime tool from an admin-defined config:
    {name, description, url, method}. If the request fails (e.g. demo/mock
    endpoint), it fails gracefully with a clear message instead of crashing
    the agent — important since company admins may configure endpoints
    that aren't live yet.
    """
    name = tool_config["name"]
    description = tool_config["description"]
    url = tool_config["url"]
    method = tool_config.get("method", "GET").upper()

    def _run(input_value: str = "") -> str:
        try:
            if method == "GET":
                resp = requests.get(url, params={"query": input_value}, timeout=6)
            else:
                resp = requests.post(url, json={"query": input_value}, timeout=6)
            resp.raise_for_status()
            return resp.text[:1500]
        except Exception as e:
            return (
                f"Tool '{name}' could not be reached right now ({type(e).__name__}). "
                "Let the user know this action isn't available at the moment."
            )

    return StructuredTool.from_function(
        func=_run,
        name=name.replace(" ", "_").lower(),
        description=description,
    )


def build_tenant_tools(tenant_id: str, company_name: str, custom_tool_configs: list) -> list:
    tools = [make_retrieval_tool(tenant_id, company_name)]
    for cfg in custom_tool_configs:
        tools.append(make_custom_tool(cfg))
    return tools
