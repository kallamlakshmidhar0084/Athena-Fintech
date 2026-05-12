# Athena RAG MVP — Mini Plan

> Focused tracker for the RAG-first sprint. Lives beside `plan.md` (which is the big roadmap).
> Each step is one focused session (1–3 hours). Check off sub-tasks as you complete them.

---

## Step 1 — Schema + Alembic
- [done] 1a. SQLAlchemy models (`base`, `tickers`, `filings`, `chunks`, `ingest_runs`)
- [ ] 1b. Alembic init + config (point at our metadata + async engine)
- [ ] 1c. First migration (autogenerate + review)
- [ ] 1d. Apply: `alembic upgrade head`
- [ ] 1e. Seed the 4 tickers (NVDA, TSLA, ICICIBANK, HDFCBANK)
- [ ] 1f. Verify in psql: `\d chunks` shows `vector(1536)` + `tsvector` columns

## Step 2 — Manual Ingest (One Filing)
- [ ] 2a. Manually download NVDA's latest 10-Q PDF, save to `data/filings/NVDA/`
- [ ] 2b. `ingest/parsers/pdf.py` — PDF → text extraction
- [ ] 2c. `ingest/chunker.py` — recursive char split, 512 tokens, 15% overlap
- [ ] 2d. `ingest/embedder.py` — OpenAI `text-embedding-3-large` @ 1536 dims
- [ ] 2e. CLI: `python -m athena.scripts.ingest_one <pdf> NVDA 10-Q 2025-Q3`
- [ ] 2f. Verify: `SELECT COUNT(*) FROM chunks WHERE filing_id = ...` returns ~80

## Step 3 — Hybrid Retriever
- [ ] 3a. `rag/retriever.py` — vector search (pgvector cosine)
- [ ] 3b. `rag/retriever.py` — BM25 search (tsvector `@@` query)
- [ ] 3c. `rag/retriever.py` — RRF fusion
- [ ] 3d. Metadata filters: `ticker`, `form_type`, `period`
- [ ] 3e. Smoke test: print top-K chunks for a sample query

## Step 4 — Reranker + Citation
- [ ] 4a. `rag/reranker.py` — Cohere Rerank v3 wrapper (free trial covers dev)
- [ ] 4b. `rag/citation.py` — post-validate cited claims
- [ ] 4c. `services/ask_service.py` — retrieve → rerank → generate with citations

## Step 5 — CLI `ask`
- [ ] 5a. `scripts/ask.py` — accepts query, prints answer + citations
- [ ] 5b. Demo: *"What did NVIDIA say about data center revenue in Q3?"*

## Step 6 — RAGAS Evals (the senior signal)
- [ ] 6a. Build golden set: 10 Q/A/source triples for NVDA
- [ ] 6b. `evals/ragas_runner.py` — faithfulness, answer relevance, context precision/recall
- [ ] 6c. CLI: `python -m athena.scripts.run_eval` prints markdown report
- [ ] 6d. Document baseline in `docs/eval-baseline.md`

---

## Status

- **Started**: 2026-05-10
- **Currently working on**: Step 1 (1a → models)
- **Decisions locked**: embedding dim = 1536 · UUID PKs · generated tsvector

---

## After This Sprint

Once Steps 1–6 are done, you have a working, evaluated RAG demo. Then we pick from `plan.md`:
- Wrap in LangGraph supervisor + Investor/Analyst personas (Phase 1.6)
- FastAPI + SSE streaming (Phase 1.8)
- Proper SEC EDGAR fetcher (Phase 1.3 properly)
- MCP server (Phase 2)
- Indic stretch (Phase 3)
