"""Stage A disables AI/legacy Mark Executed; independent manual trades remain available."""

from datetime import datetime
from typing import Any

from ..database.mongodb import MongoDB
from ..database.repositories.holding_repository import HoldingRepository
from ..database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ..database.repositories.user_transaction_repository import (
    UserTransactionRepository,
)


class OrderAlreadyFilledError(ValueError):
    """A historical fill already exists."""


class OrderNotFoundError(ValueError):
    """The historical order does not exist."""


class OrderNotExecutableError(ValueError):
    """No AI/legacy suggestion has Stage-A approval eligibility."""


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
    order = await order_repo.get(order_id)
    if order is None:
        raise OrderNotFoundError("Historical order not found")
    if order.status == "filled":
        raise OrderAlreadyFilledError("Historical order is already recorded as filled")
    # No permissive metadata flag or LLM field can bypass this boundary.
    # Recording an already-executed manual trade uses /user-transactions instead.
    raise OrderNotExecutableError(
        "Stage A: legacy/AI decisions are unverified and cannot be marked executed. "
        "Record actual trades independently with Add Transaction."
    )
