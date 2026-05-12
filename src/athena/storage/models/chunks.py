"""Chunks — the searchable rows. One per text chunk per filing.

This is where the action happens. Each chunk has:
- ``text``           — the chunk's content
- ``embedding``      — 1536-d vector for semantic similarity (pgvector)
- ``text_tsvector``  — Postgres tsvector for BM25/keyword search (generated)

Two indexes:
- HNSW on ``embedding`` — fast approximate nearest neighbor for vector search
- GIN on ``text_tsvector`` — full-text search
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from athena.storage.models.base import Base, TimestampMixin, UuidPkMixin

if TYPE_CHECKING:
    from athena.storage.models.filings import Filing


# Embedding dimension is a hard-coded decision. Changing it = re-embed everything.
# 1536 = OpenAI text-embedding-3-large truncated (matryoshka, no quality loss).
EMBEDDING_DIM = 1536


class Chunk(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "chunks"
    __table_args__ = (
        # HNSW vector index. cosine distance is the standard for embeddings.
        # m=16, ef_construction=64 are pgvector's recommended defaults.
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # GIN index on the generated tsvector column — BM25-style search
        Index(
            "ix_chunks_tsvector_gin",
            "text_tsvector",
            postgresql_using="gin",
        ),
    )

    filing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("filings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Generated column — Postgres maintains this automatically whenever `text` changes.
    # `persisted=True` => STORED (physically materialized), required for the GIN index.
    text_tsvector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', text)", persisted=True),
    )

    # The 1536-d embedding from OpenAI text-embedding-3-large @ dim=1536
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    # Metadata for citations and debugging
    token_count: Mapped[int | None] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(Text)
    char_offset: Mapped[int | None] = mapped_column(Integer)

    filing: Mapped[Filing] = relationship(back_populates="chunks")
