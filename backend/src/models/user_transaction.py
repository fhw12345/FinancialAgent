"""
User-entered transaction model — manual buy/sell records.

Distinct from PortfolioOrder (which carries AI decision rows). This is the
human's actual broker activity, used to derive Holdings via aggregation.

Schema kept minimal per v0.16.x scope:
- All transactions are POST-trade (already filled). No status, no order_type,
  no pending state. The mental model is "I really bought/sold, now record it."
- BUY → holdings.qty +=, avg_price = weighted average
- SELL → holdings.qty -=, drop row when 0, oversell raises 400
- Edits/deletes reverse-apply to holdings then re-apply.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserTransaction(BaseModel):
    """A single user-entered buy or sell that already executed."""

    transaction_id: str = Field(..., description="UUID our DB assigns")
    symbol: str = Field(..., max_length=10, description="Ticker (uppercased on write)")
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, description="Shares (positive)")
    price: float = Field(gt=0, description="Per-share execution price (USD)")
    total_amount: float = Field(
        gt=0, description="Order amount, defaults to qty*price unless user overrides"
    )
    executed_at: datetime = Field(..., description="When the trade filled")
    notes: str | None = Field(default=None, max_length=500)
    portfolio_order_id: str | None = Field(
        default=None,
        description="Set when this transaction was created via DecisionTracker "
        "Mark-Executed (back-pointer to the originating LLM-suggested order).",
    )
    created_at: datetime
    updated_at: datetime


class UserTransactionCreate(BaseModel):
    """Payload for POST /api/portfolio/transactions."""

    symbol: str = Field(..., min_length=1, max_length=10)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    total_amount: float | None = Field(
        default=None, description="If omitted, defaults to qty*price"
    )
    executed_at: datetime | None = Field(
        default=None, description="If omitted, defaults to now (UTC)"
    )
    notes: str | None = Field(default=None, max_length=500)
    portfolio_order_id: str | None = Field(
        default=None,
        description="Optional back-pointer to a portfolio_orders row when this "
        "transaction is created via Mark-Executed.",
    )


class UserTransactionUpdate(BaseModel):
    """Payload for PATCH /api/portfolio/transactions/{id}. All fields optional."""

    quantity: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)
    total_amount: float | None = Field(default=None, gt=0)
    executed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)
    # symbol + side are NOT editable; delete and re-add to change them
