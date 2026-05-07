# Athena — Code Structure & Conventions

> **Why this file exists**: On the previous project, the LangGraph agent file held all the nodes and helpers, `llm_client.py` collected unrelated functions, and `main.py` slowly absorbed business logic. This document locks in a structure that **prevents that drift**, before the first line of code is written.
>
> **Rule of thumb**: if you can't say in one sentence what a file does, it's wrong.

---

## 1. Top-Level Layout

```
Athena-Fintech/
├── plan.md
├── PlanCodeStructure.md             ← this file
├── README.md
├── pyproject.toml                   ← uv / poetry, no setup.py
├── .env.example                     ← every required env var, with comments
├── .gitignore
├── docker-compose.yml               ← postgres+pgvector, redis, (later) temporal
├── alembic.ini                      ← DB migrations
├── alembic/
│   └── versions/
│
├── src/athena/                      ← single importable package, src-layout
│   ├── __init__.py
│   ├── config.py                    ← pydantic-settings, ONE place for env reads
│   ├── logging.py                   ← structlog setup
│   │
│   ├── api/                         ← FastAPI layer (THIN)
│   ├── services/                    ← business logic (orchestration)
│   ├── agents/                      ← LangGraph agents, one folder per agent
│   ├── rag/                         ← retrieval, reranking, citations
│   ├── ingest/                      ← ingest pipeline (sources, parsers, chunker)
│   ├── tools/                       ← agent tools (market data, news, etc.)
│   ├── llm/                         ← LLM client + streaming + routing
│   ├── storage/                     ← DB models, repositories
│   ├── observability/               ← LangSmith, tracing, metrics
│   ├── workflows/                   ← Temporal workflows (Phase 4)
│   └── evals/                       ← golden sets, RAGAS runners
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── eval/                        ← regression eval suite
│
├── scripts/                         ← CLI entry points (one-liners → call services)
│   ├── ingest_filings.py
│   ├── run_eval.py
│   └── build_golden_set.py
│
├── data/                            ← gitignored
│   ├── filings/
│   ├── tearsheets/
│   └── local_dd/                    ← personal due-diligence PDFs
│
└── docs/
    ├── architecture.md
    ├── eval-baseline.md
    └── decisions/                   ← ADRs (Architecture Decision Records)
        ├── 0001-langgraph-and-temporal.md
        ├── 0002-pgvector-over-pinecone.md
        └── 0003-recursive-vs-contextual-chunking.md
```

**Hard rules**:
1. **`src/` layout** — never `import athena` working accidentally because the repo is in `sys.path`. Forces proper installation (`pip install -e .`).
2. **One package** — `src/athena/`, not `src/athena_api/` + `src/athena_core/`. Splits invite circular dependencies.
3. **No top-level `utils.py`, `helpers.py`, or `common.py`** — these always become dumping grounds. If something is truly shared, put it next to its closest concept.

---

## 2. The Layer Cake — Who Calls Whom

```
       ┌─────────────────────────────────────────┐
       │  api/         (FastAPI routes — THIN)    │
       └──────────────┬──────────────────────────┘
                      │ calls services
                      ▼
       ┌─────────────────────────────────────────┐
       │  services/    (business logic, no agents knowledge here unless wiring)
       └──────────────┬──────────────────────────┘
                      │ instantiates / runs
                      ▼
       ┌─────────────────────────────────────────┐
       │  agents/      (LangGraph supervisors + persona subgraphs)
       │  agents own:  state, nodes, prompts, tools, structured outputs
       └──────────────┬──────────────────────────┘
                      │ uses
            ┌─────────┼─────────┬───────────┐
            ▼         ▼         ▼           ▼
        rag/       tools/     llm/      storage/
       (search)  (yfinance) (claude)   (postgres)
                  (tavily)
```

**Direction is one-way**:
- `api/` may call `services/`. Never the reverse.
- `services/` may call `agents/`, `rag/`, `tools/`, `llm/`, `storage/`. Never `api/`.
- `agents/` may call `rag/`, `tools/`, `llm/`, `storage/`. Never `services/` or `api/`.
- `rag/`, `tools/`, `llm/` may call `storage/` and `llm/`. Never each other (mostly) and never anything above.

If you find yourself wanting to import "upward," you've put logic in the wrong layer.

---

## 3. The Mandatory Agent Folder Shape

This is the **single most important convention** in this repo. Every agent — supervisor, investor, analyst, compare, future personas — has the **exact same folder shape**:

```
agents/<agent_name>/
├── __init__.py          ← exports `build_<agent_name>_graph()` and `State`
├── graph.py             ← LangGraph wiring: nodes, edges, conditionals
├── nodes.py             ← One function per node. Pure-ish: (state) -> state_update
├── state.py             ← Pydantic / TypedDict for the agent's state schema
├── prompts.py           ← All prompts as named constants. No prompts elsewhere.
├── tools.py             ← Tools this agent owns (others come from src/athena/tools/)
└── outputs.py           ← Pydantic models for structured outputs
```

**Why this shape**:
- A new contributor can find anything in 10 seconds.
- A node never grows into "the prompt + the tool + the state mutation in one function."
- Prompts live as constants → version-controlled, diffable, easy to A/B.
- Tools owned by the agent stay scoped; shared tools live in the global `tools/` folder.

**Hard rules for agents**:
1. **`graph.py` builds the graph and returns it. No node logic.** It imports from `nodes.py`.
2. **`nodes.py` has one function per node.** Functions are 5–40 lines. If a node is bigger, extract a helper to a private file `_helpers.py` *inside this agent's folder*, not a global utils.
3. **No prompt strings outside `prompts.py`.** Including no inline `"You are an analyst..."` in a node. Constants only.
4. **State is Pydantic, not a free-form dict.** This catches schema drift early.
5. **Outputs are typed.** Use `outputs.py` Pydantic models with `response_format` / structured-output APIs.

### Anti-pattern (your last project)

```python
# agent.py — DON'T DO THIS (everything in one file)
def build_graph():
    g = StateGraph(...)
    def planner_node(state):
        prompt = "You are a planner..."   # prompt buried in code
        result = call_llm(prompt, state["query"])
        # ... 80 lines of branching ...
        return {...}
    g.add_node("planner", planner_node)
    # ... 12 more nodes inline ...
```

### Correct pattern

```python
# agents/supervisor/graph.py
from langgraph.graph import StateGraph
from .state import SupervisorState
from .nodes import route_intent, run_investor, run_analyst, finalize

def build_supervisor_graph():
    g = StateGraph(SupervisorState)
    g.add_node("route", route_intent)
    g.add_node("investor", run_investor)
    g.add_node("analyst", run_analyst)
    g.add_node("finalize", finalize)
    g.set_entry_point("route")
    g.add_conditional_edges("route", lambda s: s.persona, {
        "investor": "investor", "analyst": "analyst",
    })
    g.add_edge("investor", "finalize")
    g.add_edge("analyst", "finalize")
    g.set_finish_point("finalize")
    return g.compile()
```

```python
# agents/supervisor/nodes.py
from .prompts import ROUTER_PROMPT
from .state import SupervisorState
from athena.llm.client import llm

async def route_intent(state: SupervisorState) -> dict:
    decision = await llm.structured(
        prompt=ROUTER_PROMPT.format(query=state.query),
        schema=RouterDecision,
    )
    return {"persona": decision.persona, "reasoning": decision.reasoning}
```

```python
# agents/supervisor/prompts.py
ROUTER_PROMPT = """\
Classify the user's question into one of:
- investor: personal portfolio / hold-or-sell questions
- analyst: research-grade questions with sell-side framing
- compare: multi-ticker peer comparison

Question: {query}
"""
```

Now `nodes.py` is testable in isolation (mock `llm`), `prompts.py` diffs cleanly, and `graph.py` is a 15-line declaration of structure.

---

## 4. The `services/` Layer — Where Business Logic Lives

Services are the **only place** that knows how to wire an end-to-end request: load context, build the agent graph, stream results, log, persist.

```python
# services/chat_service.py
from athena.agents.supervisor import build_supervisor_graph, SupervisorState
from athena.observability.langsmith import traced

@traced(run_type="chain", name="chat_service.run")
async def run_chat(query: str, user_id: str, persona: str | None = None):
    state = SupervisorState(query=query, user_id=user_id, forced_persona=persona)
    graph = build_supervisor_graph()
    async for event in graph.astream_events(state, version="v2"):
        yield event
```

**Hard rules for services**:
1. **One service file per use case** — `chat_service.py`, `ingest_service.py`, `eval_service.py`. Not a giant `services.py`.
2. **Services don't define agents.** They *call* agent factories from `agents/`.
3. **Services are async.** API streaming requires it; sync sneaks in and breaks streaming.
4. **No HTTP knowledge in services.** Don't accept `Request` objects. Accept primitives. The `api/` layer translates.

---

## 5. The `api/` Layer — Thin Router

```
api/
├── __init__.py
├── main.py                  ← FastAPI app factory + middleware
├── deps.py                  ← FastAPI dependencies (get_db, get_user, rate_limit)
├── routes/
│   ├── chat.py              ← POST /chat (SSE)
│   ├── ingest.py
│   ├── health.py
│   └── eval.py
└── schemas/                 ← Pydantic request/response models
    ├── chat.py
    ├── ingest.py
    └── common.py
```

**Hard rules for api/**:
1. **Routes are < 30 lines.** They validate input, call a service, format output. Nothing else.
2. **No database queries in routes.** Goes through repositories via services.
3. **No prompts, no agent code, no LLM calls** in `api/`. Ever.
4. **Pydantic schemas are mandatory** on every endpoint, request and response.

---

## 6. The `llm/` Layer — Single Client, Not a Function Bag

The previous project's `llm_client.py` had `summarize()`, `extract_json()`, `classify_intent()`, `generate_html()` — a graveyard of one-off helpers. Avoid this.

```
llm/
├── __init__.py
├── client.py                ← One AsyncLLMClient class. Methods: complete, stream, structured.
├── streaming.py             ← SSE helpers (separate file because it's protocol-specific)
└── routing.py               ← (Phase 3) model selection / fallback chain
```

**One client, three methods**:

```python
# llm/client.py
class AsyncLLMClient:
    async def complete(self, prompt: str, **kw) -> str: ...
    async def stream(self, prompt: str, **kw) -> AsyncIterator[str]: ...
    async def structured(self, prompt: str, schema: Type[BaseModel], **kw) -> BaseModel: ...
```

**Hard rules for llm/**:
1. **No feature-specific helpers.** `summarize()` belongs in the agent that needs summarizing, expressed via a prompt + the structured method.
2. **One client per process** — instantiated in `config.py`, imported as `from athena.llm.client import llm`.
3. **All retries / timeouts / cost tracking happen here.** Not duplicated in every caller.

---

## 7. The `rag/` Layer — Retrieval, Independent of Agents

```
rag/
├── __init__.py
├── retriever.py             ← Hybrid retriever class (BM25 + vector + RRF)
├── reranker.py              ← Reranker wrapper
├── chunker.py               ← (used by ingest, lives here for symmetry)
├── embedder.py              ← Embedder wrapper
└── citation.py              ← Cite-claim verification post-processor
```

The RAG layer is **infrastructure**, not an agent. Any agent can call `Retriever().search(query, filters=...)`. This separation is what lets us swap retriever implementations (pgvector → Pinecone) without touching agents.

---

## 8. The `tools/` Layer — Shared Across Agents

```
tools/
├── __init__.py
├── market_data.py           ← yfinance wrapper
├── news_search.py           ← Tavily wrapper
├── peer_compare.py
├── calculator.py
└── tearsheet.py             ← poster gen, reframed
```

**Distinction with `agents/<x>/tools.py`**:
- `tools/<name>.py` (global) — used by ≥ 2 agents.
- `agents/<x>/tools.py` (local) — used by only agent `x`. Move to global if a second agent picks it up.

**Hard rules for tools/**:
1. **Each tool exposes a Pydantic input schema and a Pydantic output schema.** Tool calls are typed end-to-end.
2. **Tools are pure functions** when possible. If a tool needs DB access, take a session as a parameter — don't reach for a global.
3. **Tool descriptions in docstrings.** LLM sees the docstring; treat it as part of the prompt.

---

## 9. The `storage/` Layer — Database Boundary

```
storage/
├── __init__.py
├── db.py                    ← async SQLAlchemy session factory
├── models/                  ← SQLAlchemy ORM models
│   ├── filings.py
│   ├── chunks.py
│   ├── ingest_runs.py
│   └── tickers.py
└── repositories/            ← Repository pattern — query methods
    ├── filings_repo.py
    ├── chunks_repo.py
    └── ingest_repo.py
```

**Hard rules**:
1. **No raw SQL in services or agents.** Everything goes through a repository method.
2. **Repositories return ORM models or Pydantic DTOs, not raw rows.**
3. **Migrations are Alembic, autogenerated then reviewed.** Never write to the DB schema by hand.

---

## 10. The `ingest/` Layer

```
ingest/
├── __init__.py
├── pipeline.py              ← Orchestrates: fetch → parse → chunk → embed → index
├── sources/                 ← One file per data source
│   ├── sec_edgar.py
│   ├── bse_nse.py
│   └── earnings.py
├── parsers/
│   ├── pdf.py
│   └── html.py
├── chunker.py               ← (could also live in rag/, here it's fine — symmetric)
└── deduper.py               ← Idempotency: skip already-ingested filings
```

In Phase 4, `pipeline.py` becomes a Temporal workflow; the activities (fetch / parse / chunk / embed) are unchanged. That's the payoff of clean layering.

---

## 11. Configuration & Logging

### `config.py` — Single source of truth for settings

```python
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    anthropic_api_key: SecretStr
    openai_api_key: SecretStr
    cohere_api_key: SecretStr | None = None

    # Storage
    database_url: str = "postgresql+asyncpg://athena:athena@localhost:5432/athena"
    redis_url: str = "redis://localhost:6379/0"

    # Observability
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "athena-dev"

    # RAG knobs
    chunk_size_tokens: int = 512
    chunk_overlap_pct: float = 0.15
    retriever_top_k: int = 50
    reranker_top_n: int = 5

settings = Settings()  # imported as `from athena.config import settings`
```

**Rules**:
- Env vars are read **only here**. Never `os.getenv()` elsewhere.
- Secrets are `SecretStr`; never log them.
- RAG/LLM knobs live here, not as magic numbers in nodes.

### `logging.py` — structlog, JSON, with correlation IDs

```python
# logging.py
import structlog
from contextvars import ContextVar

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)

def configure_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )

log = structlog.get_logger()
```

**Rules**:
- All logs structured. No `print()` in `src/`.
- Every chat run has a `trace_id` injected as a context var; LangSmith uses the same.

---

## 12. Naming Conventions

| Thing | Convention | Example |
|-------|-----------|---------|
| Files | `snake_case.py` | `chat_service.py` |
| Classes | `PascalCase` | `HybridRetriever` |
| Functions / vars | `snake_case` | `run_chat`, `top_k` |
| Constants | `SCREAMING_SNAKE` | `ROUTER_PROMPT` |
| Pydantic models | `PascalCase`, suffix-explicit | `ChatRequest`, `ChatResponse`, `RetrieverResult` |
| Async functions | prefix verbs OK | `async def fetch_filings(...)` |
| Tests | mirror src tree | `tests/unit/agents/test_supervisor_nodes.py` |

**Forbidden words in filenames** (these are dumping-ground signals):
- `utils.py`, `helpers.py`, `common.py`, `misc.py`, `tools_helper.py`, `lib.py`

If you genuinely need a shared helper, name it for what it does: `text_normalization.py`, `sec_filing_parser.py`, `time_windows.py`.

---

## 13. Imports & Dependency Direction

- **Absolute imports only**: `from athena.rag.retriever import HybridRetriever`. Never `from ..retriever import ...`.
- **No cyclic imports**. If you need them, the layering is wrong — fix the layering, don't paper over with `import inside function`.
- **Public API surface per package**: each `__init__.py` exports only what's intended for external use.

```python
# agents/supervisor/__init__.py
from .graph import build_supervisor_graph
from .state import SupervisorState

__all__ = ["build_supervisor_graph", "SupervisorState"]
```

So callers do `from athena.agents.supervisor import build_supervisor_graph`, not deep imports into internals.

---

## 14. Testing Conventions

```
tests/
├── unit/                          ← fast, no IO. Mock LLM, DB, network.
│   ├── agents/
│   │   ├── test_supervisor_nodes.py
│   │   └── test_investor_nodes.py
│   ├── rag/
│   │   └── test_retriever.py
│   └── tools/
│       └── test_market_data.py
├── integration/                   ← real DB (test container), real embeddings
│   ├── test_ingest_pipeline.py
│   └── test_chat_service.py
└── eval/                          ← RAGAS golden set (slow, run nightly)
    └── test_golden_set.py
```

**Rules**:
- Unit tests **never call real LLMs or real DBs**. Use fakes.
- Integration tests use `testcontainers` to spin a Postgres in CI.
- Eval tests live separately because they're slow and probabilistic.

---

## 15. Anti-Patterns Quick Reference

| Smell | Why it's bad | Fix |
|-------|-------------|-----|
| `agent.py` with all nodes inline | Untestable, unscannable | One file per concern in `agents/<name>/` |
| `llm_client.py` with `summarize`, `classify`, `extract` | Each function is a buried prompt | Move prompts to `agents/<x>/prompts.py`; client only has `complete/stream/structured` |
| `main.py` doing config + routes + agent wiring | Bloats forever | Config in `config.py`, app factory in `api/main.py`, services in `services/` |
| `utils.py` with > 3 unrelated functions | Dumping ground | Name files for what they do |
| Prompts as f-strings inside nodes | Diff noise, no version history of prompts | All prompts as constants in `prompts.py` |
| Database session created inline in routes | Leaks, no transaction control | FastAPI dep `get_db()` in `api/deps.py` |
| `from ..something import x` (relative) | Breaks on file move | Absolute imports always |
| Tools without Pydantic schemas | LLM passes garbage args | Always typed input/output |
| Reading env vars outside `config.py` | Settings drift | One Settings class, imported everywhere |
| Mixing chunking params across ingest runs | Retrieval quality regressions | Chunking config in `config.py`, recorded as metadata on each chunk |

---

## 16. Pre-Commit Gates

Set these in `.pre-commit-config.yaml` before writing any production code:

- `ruff check --fix` — linter
- `ruff format` — formatter (replaces black)
- `mypy --strict src/athena` — type checking
- File-size guard: warn if any file in `src/athena/agents/` or `src/athena/services/` > 300 lines
- No-print check: fail if `print(` shows up in `src/`
- Forbidden filename check: fail on `utils.py`, `helpers.py`, `common.py` in `src/`

---

## 17. Architecture Decision Records (ADRs)

Every non-trivial design choice gets a short ADR in `docs/decisions/`. One page max, structured as:

```markdown
# ADR-0001: LangGraph for Agents, Temporal for Durable Workflows

Date: 2026-05-08
Status: Accepted

## Context
Need to choose orchestration for two distinct concerns: per-request agent loops
and weekly ingest workflows.

## Decision
LangGraph for in-request agents (sub-second to seconds, in-memory state, streaming).
Temporal for durable workflows (minutes to weeks, cross-process state, retries).

## Consequences
+ Each tool optimized for its job.
+ Phase 1 ships without Temporal complexity.
- Two frameworks to learn.
- Dev environment now needs Temporal in Phase 4 (docker-compose).
```

This pays off in interviews — *"why did you choose X over Y?"* gets a one-page ADR answer.

---

## 18. The 30-Second Test

Pick any file in `src/athena/`. Within 30 seconds you should be able to answer:
1. What does this file do? (one sentence)
2. Who imports from it?
3. What does it import from?

If any answer is fuzzy, the file is misplaced or doing too much. Refactor.
