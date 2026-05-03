"""
Holding model for portfolio management.

Represents a stock position in user's portfolio.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Holding(BaseModel):
    """
    Stock holding in user's portfolio.

    Tracks position quantity, cost basis, and current value.
    """

    holding_id: str = Field(..., description="Unique holding identifier")
    symbol: str = Field(..., description="Stock symbol (e.g., AAPL)")
    quantity: int = Field(..., description="Number of shares")
    avg_price: float = Field(..., description="Average purchase price per share")
    current_price: float | None = Field(None, description="Current market price")

    # Calculated fields
    cost_basis: float = Field(
        ..., description="Total amount invested (qty * avg_price)"
    )
    market_value: float | None = Field(
        None, description="Current value (qty * current_price)"
    )
    unrealized_pl: float | None = Field(None, description="Unrealized profit/loss ($)")
    unrealized_pl_pct: float | None = Field(None, description="Unrealized P/L (%)")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_price_update: datetime | None = Field(
        None, description="Last time price was updated"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "holding_id": "holding_abc123",
                "symbol": "AAPL",
                "quantity": 100,
                "avg_price": 150.50,
                "current_price": 155.25,
                "cost_basis": 15050.00,
                "market_value": 15525.00,
                "unrealized_pl": 475.00,
                "unrealized_pl_pct": 3.16,
                "created_at": "2025-11-01T10:00:00Z",
                "updated_at": "2025-11-01T10:30:00Z",
                "last_price_update": "2025-11-01T10:30:00Z",
            }
        }


class HoldingCreate(BaseModel):
    """Request model for creating a holding."""

    symbol: str = Field(..., description="Stock symbol", min_length=1, max_length=10)
    quantity: int = Field(..., description="Number of shares", gt=0)
    avg_price: float | None = Field(
        None, description="Average purchase price (auto-fetched if not provided)", gt=0
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "quantity": 100,
                "avg_price": None,  # Optional - will use current market price
            }
        }


class HoldingUpdate(BaseModel):
    """Request model for updating a holding."""

    quantity: int | None = Field(None, description="New quantity", gt=0)
    avg_price: float | None = Field(None, description="New average price", gt=0)

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "quantity": 150,
                "avg_price": 152.75,
            }
        }


class HoldingWithAnalysis(Holding):
    """
    Holding with latest analysis results.

    Extends Holding with analysis information.
    """

    latest_analysis: dict | None = Field(None, description="Latest analysis result")
    recommendation: str | None = Field(None, description="Buy/Sell/Hold recommendation")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "holding_id": "holding_abc123",
                "symbol": "AAPL",
                "quantity": 100,
                "current_price": 155.25,
                "unrealized_pl": 475.00,
                "unrealized_pl_pct": 3.16,
                "latest_analysis": {
                    "summary": "Strong uptrend with positive momentum",
                    "tools_used": ["GLOBAL_QUOTE", "RSI", "MACD"],
                    "timestamp": "2025-11-01T09:00:00Z",
                },
                "recommendation": "hold",
            }
        }
