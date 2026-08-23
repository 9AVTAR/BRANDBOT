# BrandBot 🤖
**No-code custom chatbot builder for companies** — upload your docs, get a branded AI support agent, instantly. Built and tested end-to-end (see "Testing" section — every module was actually run, not just written).

Resume bullet:
> Built and deployed BrandBot, a multi-tenant SaaS chatbot builder using LangGraph tool-calling agents, per-company isolated retrieval indexes, a no-code admin builder for custom API tools, and live token streaming — deployed on Streamlit Community Cloud.

---

## 1. What it does

A company (tenant):
1. Creates a workspace, uploads their PDFs/FAQs/docs
2. Optionally adds **custom tools** — e.g. "check_order_status" pointing at their own API — no code required, just name + description + URL
3. Gets an instant chatbot that: retrieves answers from their docs, calls their custom tools when relevant, and streams responses live
4. Gets an `<iframe>` embed snippet to drop into their own website
5. Sees basic analytics (docs uploaded, queries handled)

Each company's data and tools are fully isolated from every other company's — this is a genuine multi-tenant system, not a single shared bot.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Streamlit app.py                     │
│  ┌──────────┐   ┌────────────┐   ┌──────────────────┐    │
│  │  Chat tab │   │Builder tab │   │ Analytics tab     │    │
│  └────┬─────┘   └─────┬──────┘   └────────┬──────────┘    │
└───────┼───────────────┼──────────────────┼───────────────┘
        │               │                  │
        ▼               ▼                  ▼
   core/agent.py   core/ingestion.py   core/store.py
   (LangGraph:      (TF-IDF chunking    (tenant config:
   agent+ToolNode,   + retrieval,        name, model,
   per-tenant tools) per-tenant index)   custom tools,
        │                                 usage counts)
        ▼
   core/tools.py
   (retrieval tool +
   dynamic custom tools
   built from admin config)
```

**Per-tenant isolation, concretely:**
- Retrieval index: one `.pkl` file per `tenant_id` in `vectorstores/`
- Conversation memory: one LangGraph `thread_id` per tenant per session
- Config: one entry per `tenant_id` in `data/tenants.json`

---

## 3. Tech stack + why (interview table)

| Layer | Choice | Why |
|---|---|---|
| Agent orchestration | **LangGraph** | Tool-calling loop (`bind_tools` + `ToolNode` + `tools_condition`) — same pattern as the course, applied per-tenant |
| LLM | **Groq (Llama 3.1/3.3)** | Free tier, very fast inference — good fit for a live chat demo people will actually click through |
| Retrieval | **TF-IDF (scikit-learn)**, not a neural embedding model | Zero runtime model downloads (no HuggingFace Hub dependency at request time), tiny memory footprint — fits Streamlit Cloud's free-tier RAM limit safely. Trade-off: lexical, not semantic — see Q&A |
| Tenant config | **JSON file store** | Zero external DB setup for a demo deployment; swappable for Postgres later without touching calling code |
| Custom tools | **Runtime-built LangChain `StructuredTool`s** from admin-entered config | Lets a non-technical company admin extend the bot's abilities without writing code |
| UI | **Streamlit** | Fast to build, free hosting, streaming chat support out of the box |

---

## 4. Run locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit secrets.toml → paste your free Groq key from https://console.groq.com
streamlit run app.py
```

## 5. Deploy on Streamlit Community Cloud (for your resume link)

1. Push this folder to a new GitHub repo, e.g. `9AVTAR/brandbot`
   ```bash
   git init
   git add .
   git commit -m "BrandBot: multi-tenant LangGraph chatbot builder"
   git branch -M main
   git remote add origin https://github.com/9AVTAR/brandbot.git
   git push -u origin main
   ```
2. Go to **share.streamlit.io** → sign in with GitHub → **New app**
3. Select your repo, branch `main`, main file path `app.py`
4. Click **Advanced settings → Secrets**, paste:
   ```toml
   GROQ_API_KEY = "your-actual-key"
   ```
5. Deploy. You'll get a URL like `https://brandbot-9avtar.streamlit.app`
6. Open the app → Builder tab → paste that URL into the "embed" field so the generated `<iframe>` snippet is correct
7. Put the live URL on your resume/portfolio directly — anyone can create a demo company, upload a sample FAQ doc, and chat with it live

**Note on the free tier:** the app sleeps after inactivity and wakes on the next visit (~10-20s cold start). Mention this if asked — it's a known, explainable limitation, not a bug.

---

## 6. Testing performed (so you can speak to this confidently)

Every module below was actually executed during development, not just written:
- `core/store.py` — created, updated, and deleted a tenant end-to-end; verified persistence
- `core/ingestion.py` — ingested a sample doc, confirmed correct chunk count, ran real queries and verified correct/relevant chunks returned, and confirmed **tenant isolation** (a query against an empty tenant returns nothing, even though another tenant has matching data)
- `core/tools.py` — verified the custom-tool factory fails gracefully (no crash) against an unreachable API endpoint
- `core/agent.py` — built the actual LangGraph graph and confirmed the compiled graph's nodes and bound tools are correct
- `app.py` — ran with `streamlit run` in headless mode and confirmed it serves HTTP 200 with no startup errors



## 8. Project structure

```
brandbot/
├── app.py                          # Streamlit UI (Chat / Builder / Analytics tabs)
├── core/
│   ├── store.py                    # tenant config persistence (JSON)
│   ├── ingestion.py                # doc chunking + TF-IDF retrieval
│   ├── tools.py                    # retrieval tool + dynamic custom tool factory
│   └── agent.py                    # LangGraph agent (per-tenant tool binding)
├── data/                           # tenants.json (auto-created, gitignored)
├── vectorstores/                   # per-tenant .pkl indexes (auto-created, gitignored)
├── .streamlit/secrets.toml.example
├── requirements.txt
└── README.md
```
