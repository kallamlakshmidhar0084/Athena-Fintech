"""Tickers — master list of companies we track."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from athena.storage.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from athena.storage.models.filings import Filing


class Ticker(Base, TimestampMixin):
    """One row per tracked company.

    Symbol is the PK (NVDA, TSLA, ICICIBANK, HDFCBANK) — it's already unique,
    short, and human-readable, so no need for a surrogate UUID.
    """

    __tablename__ = "tickers"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str] = mapped_column(String(2), nullable=False)

    filings: Mapped[list[Filing]] = relationship(back_populates="ticker_obj")
