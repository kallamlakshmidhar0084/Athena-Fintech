"""Filings — one row per source document (10-K, 10-Q, annual report)."""
from __future__ import annotations

import enum
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from athena.storage.models.base import Base, TimestampMixin, UuidPkMixin

if TYPE_CHECKING:
    from athena.storage.models.chunks import Chunk
    from athena.storage.models.tickers import Ticker


class FormType(str, enum.Enum):
    """The kinds of filings we ingest."""

    K10 = "10-K"
    Q10 = "10-Q"
    K8 = "8-K"
    ANNUAL_REPORT = "ANNUAL_REPORT"      # Indian companies
    QUARTERLY_RESULT = "QUARTERLY_RESULT"


class IngestStatus(str, enum.Enum):
    """Tracks ingest pipeline progress per filing."""

    PENDING = "pending"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    DONE = "done"
    FAILED = "failed"


class Filing(Base, UuidPkMixin, TimestampMixin):
    __tablename__ = "filings"
    __table_args__ = (
        # Same filing should never be ingested twice
        UniqueConstraint("ticker", "form_type", "period_end_date", name="uq_filing"),
    )

    # FK to tickers.symbol — CASCADE so deleting a ticker removes its filings
    ticker: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("tickers.symbol", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    form_type: Mapped[FormType] = mapped_column(Enum(FormType), nullable=False)
    period_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    filed_date: Mapped[date | None] = mapped_column(Date)

    # Source metadata
    title: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(String(50))   # SEC accession number
    raw_path: Mapped[str | None] = mapped_column(Text)          # where we cached the PDF

    # Pipeline state
    ingest_status: Mapped[IngestStatus] = mapped_column(
        Enum(IngestStatus),
        default=IngestStatus.PENDING,
        nullable=False,
    )
    ingest_error: Mapped[str | None] = mapped_column(Text)

    # ORM relationships
    ticker_obj: Mapped[Ticker] = relationship(back_populates="filings")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="filing",
        cascade="all, delete-orphan",   # deleting a filing wipes its chunks
    )
