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

---

## 7. Interview Q&A

**Q1. TF-IDF kyu, proper embeddings (OpenAI/HuggingFace) kyu nahi?**
> Neural embeddings semantic matching mein better hote hain, lekin unhe runtime pe ek model download karna padta hai (ya ek paid embedding API call). Free-tier hosting pe ye ek reliability risk hai — maine khud isko test karte waqt dekha ki model download fail ho sakta hai network conditions ke hisaab se. TF-IDF completely offline hai, deterministic hai, aur FAQ/product-doc scale (jaha queries aur documents dono relatively short aur keyword-rich hote hain) pe kaafi effective hai. Trade-off honestly bolta hoon: agar company ka knowledge base bahut bada ho ya queries paraphrased/indirect ho ("how do I get my money back" for "refund policy"), tab neural embeddings zaroori ho jaate. Architecture aisi rakhi hai ki `retrieve()` function ka interface same rehte hue backend swap ho sakta hai.

**Q2. Multi-tenancy actually kaise enforce ki hai — kya guarantee hai ki ek company ka data doosri company ko nahi dikhega?**
> Har tenant ka apna separate `.pkl` index file hai jo `tenant_id` se naam hai — physically alag storage, koi shared table/namespace nahi jisme filter bhoolne se leak ho jaaye. Maine isko explicitly test kiya: ek tenant ke paas documents the, doosre (naye) tenant_id se query karne pe "no documents" response aaya — cross-contamination nahi hua.

**Q3. Custom tools admin khud API URL daal sakta hai — security risk nahi hai (SSRF jaisa)?**
> Valid concern hai. Abhi ke liye tool factory try/except mein wrapped hai taaki koi bhi failure (unreachable URL, timeout, wrong response) agent ko crash na kare — graceful degradation. Production version mein main URL allowlisting add karunga (admin sirf pre-verified domains add kar sake, ya company apne API ko ek verification step se register kare) taaki koi malicious internal URL (jaise cloud metadata endpoint) na daal sake.

**Q4. Conversation memory kaise persist hoti hai — agar user browser refresh kare toh?**
> LangGraph ka `MemorySaver` checkpointer use kiya hai, thread_id ke saath jo tenant_id + session-specific UUID se bana hai. Abhi ye in-memory hai (app restart pe reset ho jaata), Streamlit session state mein thread_id store hota hai isliye ek hi browser session ke andar continuity milti hai. Production mein `SqliteSaver` ya `PostgresSaver` mein switch karke isko durable bana sakta hoon — same LangGraph interface, sirf backend change.

**Q5. Streamlit hi kyu, proper React frontend + FastAPI backend kyu nahi?**
> Speed of iteration ke liye — Streamlit se poora multi-tab admin UI + chat + streaming ek hi file mein ban gaya, aur free deployment bhi built-in hai jo resume-ready live link ke liye perfect hai. Real limitation honestly: Streamlit single-user-per-session model follow karta hai, high-concurrency production SaaS ke liye ideal nahi. Agle step mein main FastAPI backend banake agent logic ko API ke peeche daal dunga, aur Streamlit ko sirf ek admin-preview client ki tarah rakhunga — widget khud lightweight vanilla JS se banega jo company ki site pe embed ho.

**Q6. Agent ko kaise pata chalta hai kab tool use karna hai vs seedha answer dena hai?**
> Ye LLM ka function-calling capability hai (Groq's Llama models function-calling support karte hain) — jab main tools ko `bind_tools()` se LLM ke saath bind karta hoon, LLM khud decide karta hai based on system prompt + user query ki koi tool relevant hai ya nahi. `tools_condition` LangGraph ka built-in router hai jo check karta hai ki LLM ne tool_call return kiya ya final answer — uske hisaab se graph "tools" node pe jaata hai ya "END" pe.

**Q7. Is project ko kaise scale karoge agar 50 companies use karne lagein?**
> Current bottlenecks: (1) JSON file store — concurrent writes se race condition ho sakti hai, Postgres/SQLite mein migrate karna hoga; (2) TF-IDF refit-on-every-upload — bade corpus ke liye slow ho jaayega, incremental indexing ya vector DB (Qdrant/Pinecone) chahiye hoga; (3) Streamlit ka single-process model — FastAPI + worker queue better hoga concurrent requests ke liye. Maine in sab trade-offs ko consciously choose kiya hai demo-scale ke liye, aur production path clearly pata hai.

---

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
