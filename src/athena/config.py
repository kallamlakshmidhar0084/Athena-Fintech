"""Application settings.

Single source of truth for env-driven configuration. Imported as
`from athena.config import settings`. Never call `os.getenv` elsewhere.
"""
from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    anthropic_api_key: SecretStr
    default_model: str = "claude-sonnet-4-6"
    default_max_tokens: int = 4096

    # --- Observability (optional in Phase 1) ---
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "athena-dev"
    langsmith_tracing: bool = False

    # --- Storage (Phase 1.2) ---
    database_url: str = "postgresql+asyncpg://athena:athena@localhost:5432/athena"
    redis_url: str = "redis://localhost:6379/0"

    # --- RAG knobs (Phase 1.3+) ---
    chunk_size_tokens: int = 512
    chunk_overlap_pct: float = 0.15
    retriever_top_k: int = 50
    reranker_top_n: int = 5


settings = Settings()
