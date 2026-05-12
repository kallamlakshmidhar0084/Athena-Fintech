"""Application settings.

Single source of truth for env-driven configuration. Imported as
`from athena.config import settings`. Never call `os.getenv` elsewhere.
"""
from __future__ import annotations

from pydantic import SecretStr, computed_field
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

    # --- Database (Phase 1.2) ---
    # Same DB_USER / DB_PASSWORD / DB_NAME are read by docker-compose.yml so
    # there is exactly one source of truth.
    db_user: str = "lkallam"
    db_password: SecretStr = SecretStr("password")
    db_name: str = "my_database"
    db_host: str = "localhost"
    db_port: int = 5432

    # Connection pool tuning
    db_echo: bool = False           # set true to log every SQL statement
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- RAG knobs (Phase 1.3+) ---
    chunk_size_tokens: int = 512
    chunk_overlap_pct: float = 0.15
    retriever_top_k: int = 50
    reranker_top_n: int = 5

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async SQLAlchemy DSN, built from the DB_* parts above."""
        return (
            f"postgresql+asyncpg://"
            f"{self.db_user}:{self.db_password.get_secret_value()}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = Settings()
