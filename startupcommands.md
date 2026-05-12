# Athena — Startup Commands & Architecture Cheat Sheet

> Quick reference for daily dev. See `plan.md` for roadmap, `PlanCodeStructure.md` for conventions.

---

## Why `src/athena/` (not just `athena/`)

Both layouts work. We use **src layout** for three reasons:

1. **Catches packaging mistakes early** — Python can only find `athena` via the installed pointer (`pip install -e .`), not by stumbling into a local folder. If you forget to declare a sub-package, imports break loudly in dev instead of silently in prod.
2. **Tests run against the installed package** — what CI/users would see, not your local working files.
3. **No accidental shadowing** — flat layouts can get weird if a `tests/` file name collides with a package name.

Trade-off: `pip install -e .` is a one-time step. After that, you forget about it.

---

## First-Time Setup (Run Once)

```bash
cd /Users/lkallam/Desktop/Learning/Athena-Fintech

# 1. Create venv
uv venv

# 2. Activate it
source .venv/bin/activate

# 3. Install Athena + all deps in editable mode
uv pip install -e .

# 4. Install dev tools (ruff, mypy, pytest)
uv sync --group dev

# 5. Bring up Postgres + pgAdmin + Redis
docker compose up -d

# 6. Verify pgvector
docker exec -it my_postgres_container psql -U lkallam -d my_database \
  -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector';"

# 7. Copy .env and fill in API keys
cp .env.example .env
# then edit .env → set ANTHROPIC_API_KEY
```

---

## Daily Startup (Run Each Time)

```bash
cd /Users/lkallam/Desktop/Learning/Athena-Fintech

# 1. Activate venv (once per terminal)
source .venv/bin/activate

# 2. Make sure DB stack is running (no-op if already up)
docker compose up -d

# That's it. Now run anything.
```

To shut down:
```bash
docker compose down          # stop containers, keep volume (data preserved)
docker compose down -v       # stop AND delete volume (wipes data — destructive)
```

---

## Running Files — The `-m` Rule

**Anything inside `src/athena/`** → run as a module with `-m`:

```
File path                                   Command
src/athena/llm/client.py              →     python -m athena.llm.client
src/athena/ingest/sources/edgar.py    →     python -m athena.ingest.sources.edgar
src/athena/agents/supervisor/graph.py →     python -m athena.agents.supervisor.graph
```

Translation: drop `src/`, replace `/` with `.`, drop `.py`.

The file needs an `if __name__ == "__main__":` block to actually do something when run this way.

**Anything outside `src/athena/`** → run directly:

```bash
pytest tests/unit/test_client.py        # tests
python scripts/ingest_filings.py        # scripts (when we add them)
```

---

## Common Commands

### Run the LLM smoke test
```bash
python -m athena.llm.client
```

### Run all tests
```bash
pytest                                  # everything
pytest tests/unit/                      # just unit tests
pytest tests/unit/llm/test_client.py    # one file
pytest -k "smoke" -v                    # by name pattern, verbose
```

### Run the API server (when we add FastAPI)
```bash
uvicorn athena.api.main:app --reload --port 8000
```

### Add a new dependency
```bash
uv add fastapi                          # production dep
uv add --dev pytest-cov                 # dev-only dep
uv remove litellm                       # remove a dep
```

### Lint and format
```bash
ruff check .                            # lint
ruff check . --fix                      # lint + auto-fix
ruff format .                           # format (like black)
mypy src/athena                         # type-check
```

### Database access
```bash
# psql shell (inside the container)
docker exec -it my_postgres_container psql -U lkallam -d my_database

# pgAdmin UI
open http://localhost:5050              # login: kallamlaksh@gmail.com / password

# Redis CLI
docker exec -it athena_redis redis-cli
```

### Alembic (DB migrations — when we add it)
```bash
alembic upgrade head                    # apply all migrations
alembic revision --autogenerate -m "add chunks table"   # create migration from model changes
alembic downgrade -1                    # roll back one migration
alembic current                         # show current revision
alembic history                         # list all migrations
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: athena` | venv not active OR `pip install -e .` never ran | `source .venv/bin/activate && uv pip install -e .` |
| `command not found: uv` | uv installer didn't update PATH | `source ~/.zshrc` or open a new terminal |
| `connection refused` to port 5432 | Postgres container down | `docker compose up -d` |
| `relation "filings" does not exist` | Migrations not applied | `alembic upgrade head` |
| pgAdmin won't connect to Postgres | Network mismatch in compose | Both services need same `networks:` value |
| VS Code says packages aren't installed (but smoke test works) | Wrong interpreter selected | Cmd+Shift+P → "Python: Select Interpreter" → pick `.venv/bin/python` |

---

## Architecture (One-Screen Summary)

```
Athena-Fintech/
├── pyproject.toml         # deps + tool config (ruff, mypy, pytest)
├── docker-compose.yml     # Postgres+pgvector, pgAdmin, Redis
├── .env                   # secrets (gitignored)
├── alembic/               # DB migrations (Phase 1.2)
│
└── src/athena/            # THE PACKAGE
    ├── config.py          # ONE source of truth for env vars
    ├── api/               # FastAPI routes (THIN — call services)
    ├── services/          # Business logic (orchestrate agents)
    ├── agents/            # LangGraph agents (supervisor, investor, analyst)
    │   └── <name>/        # Each agent: graph.py, nodes.py, state.py, prompts.py, tools.py, outputs.py
    ├── rag/               # Retriever, reranker, citations
    ├── ingest/            # SEC EDGAR / BSE-NSE fetchers, PDF parsers
    ├── tools/             # Shared agent tools (market data, news, tearsheet)
    ├── llm/               # AsyncLLMClient (complete / stream / structured)
    ├── storage/           # SQLAlchemy models + repositories
    ├── observability/     # LangSmith, structured logging
    └── workflows/         # Temporal workflows (Phase 4)
```

**Dependency direction (one-way)**:
```
api → services → agents → (rag, tools, llm, storage)
```

Never the reverse. If you find yourself wanting to import "upward," the file is in the wrong layer.
