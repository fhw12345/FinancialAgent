"""
Portfolio API request/response models.

Separates API layer from domain models for clean architecture.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from ...models.holding import Holding


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


class HoldingCreateRequest(BaseModel):
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
                # avg_price is optional - will use current market price if not provided
            }
        }


class HoldingUpdateRequest(BaseModel):
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


class HoldingResponse(BaseModel):
    """Response model for a holding."""

    holding_id: str = Field(..., description="Unique holding identifier")
    symbol: str = Field(..., description="Stock symbol")
    quantity: int = Field(..., description="Number of shares")
    avg_price: float = Field(..., description="Average purchase price per share")
    current_price: float | None = Field(None, description="Current market price")

    # Calculated fields
    cost_basis: float = Field(..., description="Total amount invested")
    market_value: float | None = Field(None, description="Current total value")
    unrealized_pl: float | None = Field(None, description="Unrealized profit/loss ($)")
    unrealized_pl_pct: float | None = Field(None, description="Unrealized P&L (%)")

    # Metadata
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_price_update: datetime | None = Field(
        None, description="Last time price was updated"
    )
    last_session: str | None = Field(
        None,
        description=(
            'Market session of the latest price fetch: "pre" | "regular" | '
            '"post" | "closed". None for legacy rows that predate this field.'
        ),
    )

    @classmethod
    def from_holding(cls, holding: Holding) -> "HoldingResponse":
        """Convert domain model to API response."""
        # Mongo Motor returns naive datetimes for BSON UTC fields. Re-attach UTC
        # so Pydantic serializes "...+00:00" rather than a naive "..." string,
        # which JS `new Date(str)` would otherwise interpret as local time.
        return cls(
            holding_id=holding.holding_id,
            symbol=holding.symbol,
            quantity=holding.quantity,
            avg_price=holding.avg_price,
            current_price=holding.current_price,
            cost_basis=holding.cost_basis,
            market_value=holding.market_value,
            unrealized_pl=holding.unrealized_pl,
            unrealized_pl_pct=holding.unrealized_pl_pct,
            created_at=_as_utc(holding.created_at),
            updated_at=_as_utc(holding.updated_at),
            last_price_update=_as_utc(holding.last_price_update),
            last_session=holding.last_session,
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
                "last_session": "regular",
            }
        }


class PortfolioSummaryResponse(BaseModel):
    """Response model for portfolio summary."""

    holdings_count: int = Field(..., description="Number of holdings")
    total_cost_basis: float | None = Field(
        None, description="Total amount invested across all holdings"
    )
    total_market_value: float | None = Field(
        None, description="Total current value of portfolio"
    )
    total_unrealized_pl: float | None = Field(
        None, description="Total unrealized profit/loss ($)"
    )
    total_unrealized_pl_pct: float | None = Field(
        None, description="Total unrealized P&L (%)"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "holdings_count": 3,
                "total_cost_basis": 45000.00,
                "total_market_value": 47250.00,
                "total_unrealized_pl": 2250.00,
                "total_unrealized_pl_pct": 5.0,
            }
        }


class PortfolioHistoryDataPoint(BaseModel):
    """Single data point in portfolio history."""

    timestamp: datetime = Field(..., description="Timestamp of data point")
    value: float = Field(..., description="Portfolio value at this time")


class AnalysisMarker(BaseModel):
    """Marker for an analysis event on the chart."""

    timestamp: datetime = Field(..., description="When analysis was performed")
    symbol: str = Field(..., description="Stock symbol analyzed")
    recommendation: str | None = Field(None, description="Buy/Sell/Hold recommendation")
    summary: str | None = Field(None, description="Brief analysis summary")


class OrderMarker(BaseModel):
    """Marker for a portfolio order on the chart."""

    timestamp: datetime = Field(..., description="When order was placed")
    symbol: str = Field(..., description="Stock symbol")
    side: str = Field(..., description="buy | sell")
    quantity: float = Field(..., description="Number of shares")
    status: str = Field(..., description="Order status (filled, canceled, etc.)")
    filled_avg_price: float | None = Field(None, description="Average fill price")
    order_id: str = Field(..., description="Order identifier")


class PortfolioHistoryResponse(BaseModel):
    """Response model for portfolio value history."""

    data_points: list[PortfolioHistoryDataPoint] = Field(
        ..., description="Time series data of portfolio value"
    )
    markers: list[AnalysisMarker] = Field(
        default_factory=list, description="Analysis events to show on chart"
    )
    order_markers: list[OrderMarker] = Field(
        default_factory=list, description="Order events to show on chart"
    )
    current_value: float | None = Field(None, description="Current portfolio value")
    period: str = Field(..., description="Time period of data (1D, 1M, 1Y, All)")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "data_points": [
                    {"timestamp": "2025-11-01T09:00:00Z", "value": 100000.00},
                    {"timestamp": "2025-11-01T10:00:00Z", "value": 100500.00},
                    {"timestamp": "2025-11-01T11:00:00Z", "value": 99800.00},
                ],
                "markers": [
                    {
                        "timestamp": "2025-11-01T09:30:00Z",
                        "symbol": "AAPL",
                        "recommendation": "buy",
                        "summary": "Strong uptrend, good entry point",
                    }
                ],
                "current_value": 99800.00,
                "period": "1D",
            }
        }
