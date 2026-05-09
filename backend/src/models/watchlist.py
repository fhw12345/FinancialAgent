"""
Watchlist models for tracking symbols to monitor.

Simple structure for managing user's watched stocks.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class WatchlistItem(BaseModel):
    """
    Watchlist item for a stock symbol.

    Tracks which stocks the user wants to monitor for analysis.
    """

    # Database ID
    watchlist_id: str = Field(..., description="UUID for watchlist item")

    # Stock details
    symbol: str = Field(..., description="Stock symbol (e.g., AAPL)")

    # Timestamps
    added_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When symbol was added to watchlist",
    )
    last_analyzed_at: datetime | None = Field(
        None, description="Last time this symbol was analyzed"
    )

    # Metadata
    notes: str | None = Field(None, description="Optional user notes")

    # ---- Quote snapshot (persisted to mongo since v0.27.3) ----------------
    # Filled in by GET /watchlist endpoint via best-effort live quote so the
    # UI can show current price + session next to each row, the same way
    # PortfolioSummaryTable does for holdings. Persisted (not transient) so
    # that an upstream-vendor timeout for one symbol falls back to the last
    # known value instead of rendering an empty cell. Frontend uses
    # last_price_update to mark the value as stale when older than ~5 min.
    current_price: float | None = Field(
        None, description="Last known live price; persisted snapshot"
    )
    last_price_update: datetime | None = Field(
        None, description="When the live price was last fetched (UTC)"
    )
    last_session: str | None = Field(
        None,
        description=(
            "Market session when the last quote was fetched: "
            '"pre" | "regular" | "post" | "closed"'
        ),
    )
    day_change_percent: float | None = Field(
        None,
        description="Today's percent change vs previous close from the last quote",
    )
    # W3.18 — extended-hours companion (response-only, NOT persisted to
    # mongo). Recomputed each GET from yfinance Ticker.info via the
    # DataManager's quote_ext cache. None during active pre/post sessions
    # (primary IS the ext-hours print) and when no fresh companion exists.
    ext_hours_price: float | None = Field(
        None,
        description=(
            "Companion pre/post-market price shown alongside the primary "
            "regular/closed-session price. Response-only."
        ),
    )
    ext_hours_session: str | None = Field(
        None, description='"pre" or "post" — origin of the companion price.'
    )
    ext_hours_change_percent: float | None = Field(
        None, description="Companion's % move vs the primary current_price."
    )
    ext_hours_asof: datetime | None = Field(
        None, description="Timestamp of the companion print (UTC)."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "watchlist_id": "watch_abc123",
                "symbol": "AAPL",
                "added_at": "2025-11-01T10:00:00Z",
                "last_analyzed_at": "2025-11-01T14:30:00Z",
                "notes": "High-growth tech stock",
            }
        }


class WatchlistItemCreate(BaseModel):
    """Request model for creating a watchlist item."""

    symbol: str = Field(..., description="Stock symbol", min_length=1, max_length=10)
    notes: str | None = Field(None, description="Optional user notes", max_length=500)

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "notes": "High-growth tech stock",
            }
        }
