"""Centralized model exports.

Alembic will import this module to discover all models for migration
autogeneration. Anytime you add a new model, add it here.
"""
from athena.storage.models.base import Base, TimestampMixin, UuidPkMixin
from athena.storage.models.chunks import EMBEDDING_DIM, Chunk
from athena.storage.models.filings import Filing, FormType, IngestStatus
from athena.storage.models.ingest_runs import IngestRun, RunStatus
from athena.storage.models.tickers import Ticker

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    "UuidPkMixin",
    # Tables
    "Ticker",
    "Filing",
    "Chunk",
    "IngestRun",
    # Enums
    "FormType",
    "IngestStatus",
    "RunStatus",
    # Constants
    "EMBEDDING_DIM",
]
