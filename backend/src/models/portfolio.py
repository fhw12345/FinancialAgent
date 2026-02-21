"""
Portfolio models for tracking orders and positions.

Integrates with Alpaca Paper Trading API for order execution
and provides audit trail linking orders to AI analysis.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OrderType(StrEnum):
    """Order type enum for portfolio orders."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(StrEnum):
    """Time in force enum for order duration."""

    DAY = "day"  # Valid until end of trading day
    GTC = "gtc"  # Good Till Cancelled
    IOC = "ioc"  # Immediate or Cancel
    FOK = "fok"  # Fill or Kill


class PortfolioOrder(BaseModel):
    """
    Portfolio order with native Alpaca ID and audit trail.

    Links every order to:
    1. Alpaca's native order ID (for status tracking)
    2. Our analysis ID (for audit trail: analysis → order → decision)
    3. Chat message ID (for UI display: "I placed this order because...")
    """

    # Our database ID
    order_id: str = Field(..., description="UUID for our database")

    # Foreign keys
    chat_id: str = Field(..., description="Chat where analysis happened")
    user_id: str = Field(..., description="Portfolio owner")
    message_id: str | None = Field(
        None, description="Message ID with analysis reasoning"
    )

    # Alpaca native ID (CRITICAL for status tracking)
    # None for failed orders that never reached Alpaca
    alpaca_order_id: str | None = Field(
        None, description="Alpaca's native order ID (UUID), None if order failed"
    )

    # Audit trail (CRITICAL - links order to analysis)
    analysis_id: str = Field(
        ...,
        description="Custom analysis ID used as client_order_id in Alpaca API",
    )

    # Order details
    symbol: str = Field(..., description="Stock symbol (e.g., AAPL)")
    order_type: str = Field(..., description="market | limit | stop | stop_limit")
    side: str = Field(..., description="buy | sell")
    quantity: float = Field(..., description="Number of shares")

    # Order parameters (for limit, stop, stop-limit orders)
    limit_price: float | None = Field(
        None, description="Limit price (required for limit and stop_limit orders)"
    )
    stop_price: float | None = Field(
        None, description="Stop price (required for stop and stop_limit orders)"
    )
    time_in_force: str = Field(
        "day", description="Time in force: day | gtc | ioc | fok"
    )

    # Execution details
    status: str = Field(
        ...,
        description="new | filled | partially_filled | canceled | rejected | failed",
    )
    filled_qty: float = Field(0.0, description="Shares filled")
    filled_avg_price: float | None = Field(None, description="Average fill price")
    error_message: str | None = Field(
        None, description="Error message for failed orders (raw API error)"
    )

    # Timestamps
    created_at: datetime = Field(..., description="Order placement time")
    filled_at: datetime | None = Field(None, description="Order fill time")
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Metadata
    metadata: dict = Field(
        default_factory=dict,
        description="Additional data: stop_price, limit_price, time_in_force",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "order_id": "order_abc123",
                "chat_id": "chat_xyz789",
                "user_id": "user_123",
                "message_id": "msg_456",
                "alpaca_order_id": "f8e1b8c3-7d4a-4e2f-9b1c-5a6d7e8f9a0b",
                "analysis_id": "analysis-20251101-AAPL-bullish-momentum",
                "symbol": "AAPL",
                "order_type": "market",
                "side": "buy",
                "quantity": 10.0,
                "status": "filled",
                "filled_qty": 10.0,
                "filled_avg_price": 271.17,
                "created_at": "2025-11-01T14:30:00Z",
                "filled_at": "2025-11-01T14:30:15Z",
                "metadata": {"time_in_force": "day"},
            }
        }


class PortfolioOrderInDB(PortfolioOrder):
    """Portfolio order with database ID."""

    id: str = Field(alias="_id")


class PortfolioPosition(BaseModel):
    """
    Current position in portfolio.

    Aggregates all orders for a symbol to show current holdings.
    """

    user_id: str = Field(..., description="Portfolio owner")
    symbol: str = Field(..., description="Stock symbol")

    # Position details
    quantity: float = Field(..., description="Current shares held")
    avg_entry_price: float = Field(..., description="Average purchase price")
    current_price: float | None = Field(None, description="Current market price")

    # P&L
    market_value: float | None = Field(None, description="Current market value")
    cost_basis: float = Field(..., description="Total cost basis")
    unrealized_pl: float | None = Field(None, description="Unrealized profit/loss")
    unrealized_pl_pct: float | None = Field(
        None, description="Unrealized P&L percentage"
    )

    # Timestamps
    first_acquired: datetime = Field(..., description="First purchase date")
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "symbol": "AAPL",
                "quantity": 25.0,
                "avg_entry_price": 270.50,
                "current_price": 274.80,
                "market_value": 6870.0,
                "cost_basis": 6762.50,
                "unrealized_pl": 107.50,
                "unrealized_pl_pct": 1.59,
                "first_acquired": "2025-11-01T09:35:00Z",
            }
        }


class PortfolioSummary(BaseModel):
    """Portfolio summary with total equity and P&L."""

    user_id: str = Field(..., description="Portfolio owner")

    # Account values
    equity: float = Field(..., description="Total portfolio value")
    cash: float = Field(..., description="Available cash")
    buying_power: float = Field(..., description="Buying power")

    # P&L
    total_pl: float = Field(..., description="Total profit/loss")
    total_pl_pct: float = Field(..., description="Total P&L percentage")
    day_pl: float | None = Field(None, description="Today's P&L")
    day_pl_pct: float | None = Field(None, description="Today's P&L percentage")

    # Position count
    position_count: int = Field(..., description="Number of positions")

    # Timestamp
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_123",
                "equity": 106870.0,
                "cash": 100000.0,
                "buying_power": 200000.0,
                "total_pl": 107.50,
                "total_pl_pct": 0.10,
                "day_pl": 107.50,
                "day_pl_pct": 0.10,
                "position_count": 1,
            }
        }
