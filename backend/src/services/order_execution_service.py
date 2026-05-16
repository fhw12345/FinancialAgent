"""
Order execution service — turns an LLM-suggested PortfolioOrder into an
actual UserTransaction + holdings update + cash_balance delta.

This is the "Mark Executed" workflow used by the DecisionTracker UI. We do
NOT talk to Alpaca; this is the personal-fork local path where the user
manually confirms which suggestions they actually filled.

Atomicity: MongoDB single-doc writes are atomic but we touch four documents
(user_transactions, portfolio_holdings, user_settings.cash_balance,
portfolio_orders). We use compensation: any failure mid-flow rolls back the
prior writes so the four collections stay consistent. We deliberately do
NOT use multi-doc transactions — single-user local app, the simplicity
buys more than ACID does here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from ..database.mongodb import MongoDB
from ..database.repositories.holding_repository import HoldingRepository
from ..database.repositories.portfolio_order_repository import (
    PortfolioOrderRepository,
)
from ..database.repositories.user_transaction_repository import (
    UserTransactionRepository,
)
from ..models.user_transaction import UserTransactionCreate
from .holdings_ledger import (
    NoHoldingToSellError,
    OversellError,
    apply_transaction,
)

logger = structlog.get_logger()


class OrderAlreadyFilledError(ValueError):
    """Raised when the user tries to mark-execute an already-filled order."""


class OrderNotFoundError(ValueError):
    """Raised when the order_id does not resolve."""


class OrderNotExecutableError(ValueError):
    """Raised when the order's side is HOLD/signal — nothing to execute."""


async def _adjust_cash_balance(mongodb: MongoDB, delta: float) -> float:
    """
    Atomic `$inc` on user_settings.cash_balance. Returns the post-adjust
    value. Negative deltas are allowed (BUY consumes cash) — the result
    can go negative, which is intentional per PRD: this is a personal
    tool and the user wants the warning, not a hard block.
    """
    coll = mongodb.get_collection("user_settings")
    result = await coll.find_one_and_update(
        {},
        {"$inc": {"cash_balance": delta}},
        return_document=True,
        upsert=False,
    )
    if not result:
        raise RuntimeError(
            "user_settings document missing — save settings before marking executed"
        )
    return float(result.get("cash_balance", 0.0))


async def mark_order_executed(
    *,
    mongodb: MongoDB,
    order_repo: PortfolioOrderRepository,
    tx_repo: UserTransactionRepository,
    holding_repo: HoldingRepository,
    order_id: str,
    filled_qty: float,
    filled_avg_price: float,
    executed_at: datetime,
    notes: str | None,
) -> dict[str, Any]:
    """
    Execute the four-step Mark-Executed flow. Returns a summary dict the
    API layer can hand back to the frontend.

    Steps (each step rolls back the prior ones on failure):
      1. Validate order: exists, status=suggested, side ∈ {buy, sell}
      2. Create user_transactions row (back-pointing to order_id)
      3. Apply to holdings (BUY: +qty / SELL: -qty)
      4. Adjust cash_balance ($inc; BUY: -total / SELL: +total)
      5. Mark order filled (status=filled, fill columns, user_transaction_id)
    """

    order = await order_repo.get(order_id)
    if order is None:
        raise OrderNotFoundError(f"order {order_id} not found")
    if order.status == "filled":
        raise OrderAlreadyFilledError(
            f"order {order_id} already executed at {order.filled_at}"
        )
    if order.side not in ("buy", "sell"):
        raise OrderNotExecutableError(
            f"order {order_id} side={order.side!r} is not executable "
            "(only buy/sell can be marked executed)"
        )

    total = round(filled_qty * filled_avg_price, 4)
    cash_delta = -total if order.side == "buy" else total

    # Step 2: create transaction (with back-pointer)
    tx_payload = UserTransactionCreate(
        symbol=order.symbol,
        side=order.side,  # type: ignore[arg-type]
        quantity=filled_qty,
        price=filled_avg_price,
        total_amount=total,
        executed_at=executed_at,
        notes=notes,
        portfolio_order_id=order_id,
    )
    tx = await tx_repo.create(tx_payload)

    # Step 3: apply to holdings
    try:
        await apply_transaction(tx, holding_repo, sign=1)
    except (OversellError, NoHoldingToSellError) as e:
        await tx_repo.delete(tx.transaction_id)
        raise ValueError(str(e)) from e
    except Exception as e:
        await tx_repo.delete(tx.transaction_id)
        logger.error("mark_executed_holdings_apply_failed", error=str(e))
        raise

    # Step 4: adjust cash
    try:
        new_cash = await _adjust_cash_balance(mongodb, cash_delta)
    except Exception as e:
        # Roll back holdings + tx
        await apply_transaction(tx, holding_repo, sign=-1)
        await tx_repo.delete(tx.transaction_id)
        logger.error("mark_executed_cash_adjust_failed", error=str(e))
        raise

    # Step 5: mark order filled
    updated_order = await order_repo.mark_filled(
        order_id=order_id,
        filled_qty=filled_qty,
        filled_avg_price=filled_avg_price,
        filled_at=executed_at,
        user_transaction_id=tx.transaction_id,
    )
    if updated_order is None:
        # Roll back cash, holdings, tx — the order vanished mid-flow
        await _adjust_cash_balance(mongodb, -cash_delta)
        await apply_transaction(tx, holding_repo, sign=-1)
        await tx_repo.delete(tx.transaction_id)
        raise OrderNotFoundError(f"order {order_id} disappeared while marking filled")

    cash_warning = (
        f"cash_balance is now {new_cash:.2f} (negative — BUY exceeded available cash)"
        if new_cash < 0
        else None
    )

    logger.info(
        "order_marked_executed",
        order_id=order_id,
        symbol=order.symbol,
        side=order.side,
        filled_qty=filled_qty,
        filled_avg_price=filled_avg_price,
        cash_delta=cash_delta,
        new_cash_balance=new_cash,
        transaction_id=tx.transaction_id,
    )

    return {
        "order_id": order_id,
        "transaction_id": tx.transaction_id,
        "symbol": order.symbol,
        "side": order.side,
        "filled_qty": filled_qty,
        "filled_avg_price": filled_avg_price,
        "filled_at": executed_at.isoformat(),
        "cash_delta": cash_delta,
        "new_cash_balance": new_cash,
        "cash_warning": cash_warning,
    }
