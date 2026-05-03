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
