"""Ingest run audit log. One row per ingest invocation."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from athena.storage.models.base import Base, TimestampMixin, UuidPkMixin


class RunStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class IngestRun(Base, UuidPkMixin, TimestampMixin):
    """Audit row for each ingest job — useful for replays and debugging."""

    __tablename__ = "ingest_runs"

    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus),
        default=RunStatus.RUNNING,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ticker_filter: Mapped[str | None] = mapped_column(String(20))

    # Free-form stats blob: {docs_processed: 3, chunks_created: 240, errors: 0, ...}
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    error: Mapped[str | None] = mapped_column(Text)
