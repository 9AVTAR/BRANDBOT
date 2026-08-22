"""
BrandBot — No-code custom chatbot builder for companies.

A company (tenant) uploads its docs, optionally configures custom tools
(API-backed actions like "check order status"), and instantly gets a
branded chatbot that can be tested here or embedded on their own site.

Run locally:  streamlit run app.py
Deploy:       Streamlit Community Cloud (see README.md)
"""

import os
import tempfile
import uuid

import streamlit as st

from core import store
from core.agent import get_agent
from core.ingestion import ingest_file, doc_count

st.set_page_config(page_title="BrandBot", page_icon="🤖", layout="wide")

# ---------- Embed mode: a company embeds BrandBot on their own site as
# <iframe src=".../?tenant=<id>&embed=1"> — only the chat widget renders. ----
query_params = st.query_params
embed_mode = query_params.get("embed") == "1"
preselected_tenant = query_params.get("tenant")


def render_chat(tenant: dict, embedded: bool = False):
    if not embedded:
        st.subheader(f"💬 Chat with {tenant['name']}'s Assistant")

    if not st.secrets.get("GROQ_API_KEY"):
        st.warning(
            "GROQ_API_KEY not set in Streamlit secrets — the chatbot can't call "
            "the LLM yet. Add it under Settings → Secrets to enable live chat."
        )
        return

    if doc_count(tenant["id"]) == 0:
        st.info("This company hasn't uploaded any documents yet — the assistant will have no knowledge base to search.")

    session_key = f"messages_{tenant['id']}"
    if session_key not in st.session_state:
        st.session_state[session_key] = []

    for msg in st.session_state[session_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input(f"Ask {tenant['name']} anything...")
    if prompt:
        st.session_state[session_key].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        agent = get_agent(
            tenant["id"], tenant["name"], tenant["model"], tenant.get("custom_tools", [])
        )
        thread_id = st.session_state.setdefault(f"thread_{tenant['id']}", str(uuid.uuid4()))
        config = {"configurable": {"thread_id": thread_id}}

        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_response = ""
            try:
                for chunk, metadata in agent.stream(
                    {"messages": [{"role": "user", "content": prompt}]},
                    config,
                    stream_mode="messages",
                ):
                    # Only render tokens coming from the final LLM answer node,
                    # not intermediate tool-call chunks, so the UI stays clean.
                    if metadata.get("langgraph_node") == "agent" and getattr(chunk, "content", None):
                        full_response += chunk.content
                        placeholder.markdown(full_response + "▌")
                placeholder.markdown(full_response or "_(no text response)_")
            except Exception as e:
                full_response = f"Sorry, something went wrong on my end: {e}"
                placeholder.markdown(full_response)

        st.session_state[session_key].append({"role": "assistant", "content": full_response})
        store.increment_query_count(tenant["id"])


# ============================== EMBED MODE ===================================
if embed_mode and preselected_tenant:
    tenant = store.get_tenant(preselected_tenant)
    if not tenant:
        st.error("Unknown chatbot — check the embed link.")
    else:
        st.markdown(
            f"<h4 style='color:{tenant['brand_color']}'>{tenant['name']}</h4>",
            unsafe_allow_html=True,
        )
        render_chat(tenant, embedded=True)
    st.stop()

# ============================== FULL BUILDER APP =============================
st.title("🤖 BrandBot")
st.caption("Upload your company's docs → get a custom AI chatbot, instantly.")

tenants = store.list_tenants()

with st.sidebar:
    st.header("Companies")
    tenant_names = {tid: t["name"] for tid, t in tenants.items()}

    if tenant_names:
        selected_id = st.selectbox(
            "Select a company",
            options=list(tenant_names.keys()),
            format_func=lambda tid: tenant_names[tid],
            index=list(tenant_names.keys()).index(preselected_tenant)
            if preselected_tenant in tenant_names
            else 0,
        )
    else:
        selected_id = None
        st.info("No companies yet — create one below.")

    st.divider()
    st.subheader("+ New company")
    new_name = st.text_input("Company name", key="new_company_name")
    new_color = st.color_picker("Brand color", "#4F46E5")
    new_model = st.selectbox(
        "Model", ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3-27b"], key="new_model"
    )
    if st.button("Create company", use_container_width=True):
        if new_name.strip():
            tid = store.create_tenant(new_name.strip(), new_color, new_model)
            st.success(f"Created '{new_name}' — tenant ID: {tid}")
            st.rerun()
        else:
            st.error("Enter a company name first.")

if not selected_id:
    st.stop()

tenant = store.get_tenant(selected_id)

tab_chat, tab_builder, tab_analytics = st.tabs(["💬 Chat", "🛠️ Builder", "📊 Analytics"])

# ---------------------------- Chat tab ----------------------------
with tab_chat:
    render_chat(tenant)

# ---------------------------- Builder tab ----------------------------
with tab_builder:
    st.subheader("Knowledge base")
    uploaded = st.file_uploader(
        "Upload PDFs or text files (FAQs, product docs, policies)",
        type=["pdf", "txt"],
        accept_multiple_files=True,
    )
    if uploaded and st.button("Ingest documents"):
        total_chunks = 0
        for f in uploaded:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(f.name)[1]) as tmp:
                tmp.write(f.read())
                tmp_path = tmp.name
            n = ingest_file(tenant["id"], tmp_path, f.name)
            os.unlink(tmp_path)
            total_chunks += n
        store.increment_doc_count(tenant["id"], len(uploaded))
        st.success(f"Ingested {len(uploaded)} file(s) → {total_chunks} chunks added to the knowledge base.")
        st.rerun()

    st.metric("Chunks currently in knowledge base", doc_count(tenant["id"]))

    st.divider()
    st.subheader("Custom tools (actions your bot can take)")
    st.caption(
        "Example: name='check_order_status', description='Look up an order by ID', "
        "url='https://yourapi.com/orders', method='GET'. The LLM decides on its own "
        "when a user's question needs this tool."
    )
    for t in tenant.get("custom_tools", []):
        st.code(f"{t['name']}  ({t['method']} {t['url']})\n{t['description']}", language=None)

    with st.form("add_tool_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        tool_name = col1.text_input("Tool name")
        tool_method = col2.selectbox("Method", ["GET", "POST"])
        tool_desc = st.text_area("Description (tells the LLM when to use this tool)")
        tool_url = st.text_input("API URL")
        if st.form_submit_button("Add tool"):
            if tool_name and tool_desc and tool_url:
                store.add_custom_tool(tenant["id"], tool_name, tool_desc, tool_url, tool_method)
                st.success(f"Added tool '{tool_name}'.")
                st.rerun()
            else:
                st.error("Fill in all fields.")

    st.divider()
    st.subheader("Embed on your website")
    app_url = st.text_input("Your deployed BrandBot URL (fill after deploying)", "https://your-app.streamlit.app")
    embed_url = f"{app_url}/?embed=1&tenant={tenant['id']}"
    st.code(f'<iframe src="{embed_url}" width="380" height="560" style="border:none;"></iframe>', language="html")

    st.divider()
    if st.button("🗑️ Delete this company", type="secondary"):
        store.delete_tenant(tenant["id"])
        st.rerun()

# ---------------------------- Analytics tab ----------------------------
with tab_analytics:
    st.subheader(f"Analytics — {tenant['name']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Documents uploaded", tenant.get("doc_count", 0))
    c2.metric("Knowledge base chunks", doc_count(tenant["id"]))
    c3.metric("Total queries handled", tenant.get("query_count", 0))
    st.caption("In a production version this would break down by resolved vs. escalated, cost per model, and response latency.")
