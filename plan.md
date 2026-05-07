# Athena — Investment Intelligence Co-Pilot

> **One-liner**: A senior-grade GenAI co-pilot for equity research, built on hybrid RAG over public filings and earnings transcripts, with agentic tool use and MCP-backed real-time data — designed to demo to **JPMorgan, Goldman, Morgan Stanley, AlphaSense, Bloomberg, MSCI, Zerodha, Sarvam AI** and similar.

---

## Locked-In Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tickers (Phase 1) | **NVDA, TSLA, ICICIBANK, HDFCBANK** | 2 US tech + 2 Indian banks → cross-market peer compare is a *killer demo*, hits big-fin + Indian roles |
| Primary persona modes | **Investor** + **Analyst** | Investor = personally usable (demo enthusiasm); Analyst = JPM/GS/AlphaSense signal |
| Agent framework | **LangGraph** for in-request orchestration | Mature, observable via LangSmith, native streaming |
| Durable workflows | **Temporal** (Phase 4 only — not Phase 1) | Used for weekly ingest + scheduled evals; *not* for the chat loop. See "Temporal vs LangGraph" below |
| Vector store | **pgvector** on Postgres | Single store for filings + chunks + metadata, hybrid (BM25 via `tsvector`) without adding infra |
| Observability | **LangSmith** + structured logs | Traces every agent run end-to-end |
| LLMs | **Claude 4.7 (primary)** + GPT-4 / Gemini fallback | Claude for reasoning over long filings; routing in Phase 3 |
| Embeddings | **OpenAI `text-embedding-3-large`** to start | Switch to BGE-large self-host if cost matters in Phase 3 |
| Reranker | **Cohere Rerank v3** | Or `bge-reranker-v2-m3` if self-hosting |
| API layer | **FastAPI** + SSE streaming | Chapter-1-aligned, async-native |

---

## Temporal vs LangGraph — Where Each Lives

These are **not alternatives**. Different layers, different jobs.

| Layer | Tool | Lifetime | Examples in Athena |
|-------|------|----------|--------------------|
| Per-request agent loop | **LangGraph** | Seconds | "User asks question → router → RAG → tool calls → answer" |
| Scheduled / long-running | **Temporal** | Minutes to weeks | Weekly filing ingest, nightly RAGAS eval, ESG report processing pipeline |

**Rule of thumb**: if the work needs to **survive process restarts** or **wait for an external event** (cron, webhook, human approval), it belongs in Temporal. If it happens inside one chat reply, LangGraph.

**Phase 1 deliberately skips Temporal** — we'll use a simple cron / one-shot script for the initial ingest. Adding Temporal too early is over-engineering. We bring it in Phase 4 when the ingest cadence becomes weekly + retry-prone.

---

## Phase 1 — Core RAG + Investor & Analyst Modes (3 weeks)

**Goal**: A working chat UI where you can ask **investor-mode** questions ("Should I hold NVDA?") and **analyst-mode** questions ("Compare HDFC vs ICICI NPA trend") about the 4 tickers, with cite-grounded answers from real filings.

**Success criteria**:
- 30-question golden eval set passing **≥0.7 faithfulness** (RAGAS) and **≥0.8 context recall**
- p95 chat latency under 8s (with streaming, perceived latency < 2s)
- Every answer has at least one verifiable citation (page-level for PDFs)
- Code structure passes the rules in `PlanCodeStructure.md` (no >300-line files in `agents/` or `services/`)

**Deliverables**:
- Ingest pipeline for 8 quarters of 10-K/10-Q (NVDA, TSLA) + annual reports & quarterly results (ICICI, HDFC)
- Hybrid RAG (pgvector + tsvector BM25 + RRF fusion + Cohere rerank)
- LangGraph supervisor with two persona subgraphs (Investor, Analyst)
- 3 starter tools: `lookup_market_data` (yfinance), `search_news` (Tavily), `compare_filings`
- FastAPI `/chat` endpoint with SSE streaming
- LangSmith tracing on every run
- Initial RAGAS eval harness
- Basic web UI (or `curl` examples are fine for now)

### Phase 1 Checklist

#### 1.1 Project bootstrap
- [ ] Repo scaffold per `PlanCodeStructure.md`
- [ ] `pyproject.toml` (uv preferred), `.env.example`, `.gitignore`
- [ ] `docker-compose.yml`: Postgres 16 + pgvector + Redis
- [ ] `pydantic-settings` config in `src/athena/config.py`
- [ ] Structured logging (`structlog`) wired in `src/athena/logging.py`
- [ ] Pre-commit: `ruff`, `black`, `mypy --strict`

#### 1.2 Storage & schema
- [ ] Alembic migrations baseline
- [ ] Tables: `filings`, `chunks`, `embeddings`, `tickers`, `ingest_runs`
- [ ] `pgvector` extension + HNSW index on `chunks.embedding`
- [ ] `tsvector` GIN index on `chunks.text` for BM25
- [ ] Repository pattern (`storage/repositories/*`)

#### 1.3 Ingest pipeline (one-shot script for Phase 1)
- [ ] `ingest/sources/sec_edgar.py` — fetch 10-K/10-Q for NVDA, TSLA (8 quarters back)
- [ ] `ingest/sources/bse_nse.py` — fetch annual report + quarterly results for ICICIBANK, HDFCBANK
- [ ] `ingest/parsers/pdf.py` — Docling or `unstructured` (handle tables + multi-column)
- [ ] `ingest/chunker.py` — recursive char split, 512 tokens, 15% overlap, store `(page, section)` metadata
- [ ] `ingest/embedder.py` — batched OpenAI embeddings, idempotent on `(filing_id, chunk_idx)`
- [ ] CLI: `python -m athena.scripts.ingest_filings --tickers NVDA,TSLA,ICICIBANK,HDFCBANK`
- [ ] Verify: 4 tickers × ~12 docs × ~80 chunks/doc ≈ 4K chunks in pgvector

#### 1.4 RAG layer
- [ ] `rag/retriever.py` — hybrid: vector (pgvector) + BM25 (tsvector), RRF fusion
- [ ] `rag/reranker.py` — Cohere Rerank v3 wrapper, top-50 → top-5
- [ ] `rag/citation.py` — post-process to verify every `[id]` claim has overlap with chunk
- [ ] Metadata filters: `ticker`, `form_type`, `period`, `language`
- [ ] Unit tests on retriever with seeded data

#### 1.5 LLM client layer
- [ ] `llm/client.py` — single async client factory; one entry point per provider, no per-feature functions
- [ ] `llm/streaming.py` — SSE token streaming helper
- [ ] Request-level cost + token tracking → emitted as a structured log

#### 1.6 Agents
- [ ] `agents/supervisor/` — router that chooses Investor vs Analyst based on query intent
- [ ] `agents/investor/` — persona-specific prompts, plain-English citations
- [ ] `agents/analyst/` — persona-specific prompts, sell-side report tone
- [ ] Each agent folder follows the mandatory shape in `PlanCodeStructure.md` (graph.py, nodes.py, state.py, prompts.py, tools.py, outputs.py)
- [ ] Pydantic structured outputs for both modes

#### 1.7 Tools
- [ ] `tools/market_data.py` — yfinance wrapper, cached 60s
- [ ] `tools/news_search.py` — Tavily, scoped to ticker
- [ ] `tools/peer_compare.py` — multi-ticker filing comparison helper
- [ ] All tools registered with explicit Pydantic input/output schemas

#### 1.8 API layer
- [ ] `POST /chat` (SSE streaming, accepts `{query, persona?, ticker?}`)
- [ ] `POST /ingest/admin` (gated by API key)
- [ ] `GET /health` (DB + LLM provider checks)
- [ ] Request validation via Pydantic schemas
- [ ] Auth: simple API-key header for now (proper in Phase 3)

#### 1.9 Observability
- [ ] LangSmith project setup, env vars wired
- [ ] Trace metadata: `persona`, `ticker`, `tool_calls`, `tokens`, `latency_ms`
- [ ] Cost dashboard (LangSmith or simple Postgres rollup)

#### 1.10 Evals (the senior signal)
- [ ] Build golden set: 30 Q/A/source triples (10 investor, 10 analyst, 10 cross-ticker compare)
- [ ] `evals/ragas_runner.py` — faithfulness, answer relevance, context precision/recall
- [ ] CLI: `python -m athena.scripts.run_eval` produces a markdown report
- [ ] Document baseline numbers in `docs/eval-baseline.md`

#### 1.11 Demo
- [ ] Minimal Streamlit or Next.js chat UI (one page, persona selector + ticker dropdown)
- [ ] Record a 3-min Loom showing: persona switch, hybrid retrieval citations, peer compare
- [ ] README with quickstart

---

## Phase 2 — MCP + Tearsheet Generator + Compare Mode (1.5 weeks)

**Goal**: Add the Compare persona, plug in MCP servers (filesystem + custom EDGAR/BSE), and bring back your **poster generation as a tearsheet tool** — making it a real artifact analysts produce.

**Success criteria**:
- Custom MCP server exposes filings as resources + a `search_filings` tool
- Filesystem MCP lets the agent read your local DD docs
- Tearsheet generator produces a 1-page PDF/HTML for any ticker
- Compare persona supports up to 4 tickers in one query

### Phase 2 Checklist

#### 2.1 MCP integration
- [ ] Custom Athena MCP server (Python `mcp` SDK)
  - [ ] `resources://filings/{ticker}/{form}/{period}` — exposes raw filing chunks
  - [ ] `tools/search_filings(query, ticker?, form?)` — gateway to RAG
  - [ ] `tools/get_market_quote(ticker)` — yfinance passthrough
- [ ] Wire filesystem MCP for local PDFs in `data/local_dd/`
- [ ] Document MCP server config in `docs/mcp.md`

#### 2.2 Compare persona
- [ ] `agents/compare/` — peer-comparison subgraph
- [ ] Multi-ticker retrieval (interleaved per ticker, not naively merged)
- [ ] Output schema: side-by-side table + narrative summary

#### 2.3 Tearsheet generator (your existing poster gen, retooled)
- [ ] `tools/tearsheet.py` — input: ticker + sections requested
- [ ] Reuse design agent → HTML/CSS, but template-aware
- [ ] Standard sections: snapshot, KPIs, risk factors, recent news, peer position
- [ ] Saved to `data/tearsheets/<ticker>_<date>.html`

#### 2.4 Stretch within phase
- [ ] Prompt caching on the system prompt + retrieved chunks (Anthropic)
- [ ] Contextual chunking (Anthropic 2024 pattern) at re-ingest

---

## Phase 3 — Production Hardening + Indic Stretch (2 weeks)

**Goal**: Make Athena interview-demo-ready end-to-end. Add the Indic differentiator that no US candidate brings.

### Phase 3 Checklist

#### 3.1 Production basics
- [ ] Auth: per-user API keys + per-key rate limits (token-bucket via Redis)
- [ ] Caching: semantic cache for common questions (Redis + similarity threshold)
- [ ] Model routing: cheap model for intent classification, frontier for synthesis
- [ ] Cost tracking per user / per ticker / per persona
- [ ] Graceful degradation when LLM provider 5xx (fallback chain)
- [ ] Background async ingest queue (Celery or RQ — Temporal comes in Phase 4)

#### 3.2 Indic stretch
- [ ] Hindi/Hinglish query routing via Sarvam-1 (small router LLM)
- [ ] Translate answer back to query language
- [ ] Test on Hinglish queries: *"ICICI ka NPA trend kya hai last 4 quarters mein?"*

#### 3.3 Eval expansion
- [ ] Golden set → 100 questions
- [ ] Add LLM-as-judge for harder qualitative metrics
- [ ] CI pipeline: every PR runs eval, blocks if faithfulness drops > 5%

#### 3.4 Safety
- [ ] Prompt-injection guards on retrieved chunks (Llama Guard or Lakera)
- [ ] PII scrubbing at ingest
- [ ] Output filter for unverified financial claims ("Athena cannot give investment advice")

---

## Phase 4 — Temporal Workflows + Scale (1.5 weeks)

**Goal**: Replace the Phase 1 one-shot ingest with a proper **durable Temporal workflow** that runs weekly, recovers from failures, and supports the broader corpus (NIFTY 50 + S&P 500).

### Phase 4 Checklist

#### 4.1 Temporal setup
- [ ] Temporal Cloud or self-hosted via docker-compose
- [ ] Workflow: `WeeklyIngestWorkflow` (parameterized by ticker list)
- [ ] Activities: `fetch_filings`, `parse_pdf`, `chunk`, `embed`, `index`
- [ ] Retry policies per activity type (network: aggressive; LLM: backoff)
- [ ] Cron schedule: every Saturday 02:00 IST

#### 4.2 Scale corpus
- [ ] Expand to NIFTY 50 + S&P 500 (~550 tickers)
- [ ] Sharded ingest workflow (parallelism = 20)
- [ ] Idempotency on `(filing_id, chunk_idx)` so re-runs are safe

#### 4.3 Scheduled evals
- [ ] `NightlyEvalWorkflow` — runs RAGAS, alerts on regression
- [ ] Evidence dashboard: trend of faithfulness over commits

#### 4.4 Stretch verticals (each becomes a 2-day extension)
- [ ] Earnings call shift detector (Persona 4)
- [ ] ESG analyst (Persona 5) — adds sustainability report ingest
- [ ] Credit memo writer (Persona 6)
- [ ] M&A comparable transactions (Persona 7)
- [ ] Regulatory tracker (Persona 8) — SEBI/RBI/SEC circulars

---

## What "Done" Looks Like

By the end of Phase 4, you can put this on your resume:

> **Athena** — Investment Intelligence Co-Pilot. Built on LangGraph + Temporal with hybrid RAG (pgvector + BM25 + Cohere rerank, contextual chunking) over 1,500+ SEC and BSE/NSE filings. Multi-persona supervisor agent (Investor / Analyst / Compare / ESG). MCP-backed filing server and filesystem integration. Multilingual query support (Hindi/English/Hinglish via Sarvam-1). RAGAS-evaluated retrieval pipeline with CI gating. LangSmith observability. Live demo: cite-grounded peer comparison across NVIDIA, Tesla, ICICI, and HDFC over 8 quarters of filings.

That sentence opens doors at **JPMorgan, Goldman, Morgan Stanley, BlackRock, Bloomberg, AlphaSense, Hebbia, MSCI, Zerodha, Razorpay, Sarvam AI**, and the BFSI practices of **TCS, Infosys, Wipro**.

---

## Next Steps

1. Read `PlanCodeStructure.md` (next file) — it locks in the folder structure that prevents the bloat you hit on your last project.
2. We'll deep-dive Phase 1.1 — 1.3 (bootstrap + storage + ingest) in the next conversation, including the actual SEC EDGAR fetcher code (it has gotchas: CIK lookup, filing index parsing, polite User-Agent requirement).
3. Confirm tickers / let me know if you want to swap any.

## Open Questions for You

- [ ] Are you OK with **uv** as the package manager (faster than poetry, modern)? Or prefer poetry?
- [ ] Streamlit demo UI for Phase 1 (faster) or jump straight to Next.js (closer to production)?
- [ ] Do you have an Anthropic API key + OpenAI key + Cohere trial ready, or do we need a setup checklist?
- [ ] Run Postgres in docker-compose locally, or use a managed (Supabase / Neon) free tier?
