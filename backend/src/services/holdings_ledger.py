"""
Holdings ledger — applies a UserTransaction to the holdings collection.

BUY → qty += new_qty, avg_price = weighted average of existing + new lot
SELL → qty -= new_qty; deletes the row when qty hits 0; oversell raises ValueError

Used by the transactions API on create / edit / delete to keep holdings in
lockstep with the transaction log.
"""

from __future__ import annotations

import structlog

from ..database.repositories.holding_repository import HoldingRepository
from ..models.holding import HoldingCreate, HoldingUpdate
from ..models.user_transaction import UserTransaction

logger = structlog.get_logger(__name__)


class OversellError(ValueError):
    """Raised when a SELL would push holding qty below zero."""


class NoHoldingToSellError(ValueError):
    """Raised when trying to SELL a symbol the user does not hold."""


async def apply_transaction(
    tx: UserTransaction, repo: HoldingRepository, *, sign: int = 1
) -> None:
    """
    Apply `tx` to holdings. sign=1 forward (create), sign=-1 reverse (delete/edit).

    For edits we reverse-apply the old version then forward-apply the new one
    (caller orchestrates; this helper only does one direction).

    Raises OversellError / NoHoldingToSellError when the math goes negative.
    """
    if sign not in (1, -1):
        raise ValueError("sign must be 1 or -1")

    direction = tx.side  # "buy" or "sell"
    # Effective quantity change to holdings
    # forward BUY  → +qty,  reverse BUY  → -qty
    # forward SELL → -qty,  reverse SELL → +qty
    delta = tx.quantity if direction == "buy" else -tx.quantity
    delta *= sign

    existing = await repo.get_by_symbol(symbol=tx.symbol)

    if existing is None:
        if delta <= 0:
            # Nothing to subtract from
            raise NoHoldingToSellError(
                f"Cannot {direction} {tx.symbol}: no existing holding"
            )
        # Create new holding from a forward BUY (or reverse SELL, conceptually
        # restoring shares the user previously sold).
        await repo.create(
            holding_create=HoldingCreate(
                symbol=tx.symbol, quantity=int(delta), avg_price=tx.price
            )
        )
        logger.info(
            "holding_created_from_tx", symbol=tx.symbol, qty=delta, price=tx.price
        )
        return

    new_qty = existing.quantity + delta
    if new_qty < 0:
        raise OversellError(
            f"Cannot sell {tx.quantity} {tx.symbol}: only {existing.quantity} held"
        )
    if new_qty == 0:
        await repo.delete(existing.holding_id)
        logger.info("holding_deleted_from_tx", symbol=tx.symbol)
        return

    if delta > 0:
        # Forward BUY (or reverse SELL): weighted-avg the new lot in.
        # cost basis grows by tx.price * delta
        new_cost = (existing.quantity * existing.avg_price) + (delta * tx.price)
        new_avg = new_cost / new_qty
        await repo.update(
            existing.holding_id,
            HoldingUpdate(quantity=int(new_qty), avg_price=round(new_avg, 4)),
        )
        logger.info(
            "holding_updated_from_buy",
            symbol=tx.symbol,
            new_qty=new_qty,
            new_avg=round(new_avg, 4),
        )
    else:
        # Forward SELL (or reverse BUY): qty drops, avg_price stays the same
        # (cost basis convention: SELL realizes P&L, doesn't reprice the lot).
        await repo.update(existing.holding_id, HoldingUpdate(quantity=int(new_qty)))
        logger.info(
            "holding_updated_from_sell",
            symbol=tx.symbol,
            new_qty=new_qty,
            avg_unchanged=existing.avg_price,
        )
