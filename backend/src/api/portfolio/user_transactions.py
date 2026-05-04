"""
User-entered transactions endpoints.
GET / POST / PATCH / DELETE under /api/portfolio/transactions.

Each create/update/delete also reverse-and-forward applies to the holdings
collection so the two stay in lockstep.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from ...database.mongodb import MongoDB
from ...database.repositories.holding_repository import HoldingRepository
from ...database.repositories.user_transaction_repository import (
    UserTransactionRepository,
)
from ...models.user_transaction import (
    UserTransaction,
    UserTransactionCreate,
    UserTransactionUpdate,
)
from ...services.holdings_ledger import (
    NoHoldingToSellError,
    OversellError,
    apply_transaction,
)
from ..dependencies.auth import get_mongodb
from ..dependencies.portfolio_deps import get_holding_repository
from ..dependencies.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter()


def get_user_tx_repo(
    mongodb: MongoDB = Depends(get_mongodb),
) -> UserTransactionRepository:
    return UserTransactionRepository(mongodb.get_collection("user_transactions"))


@router.get("/user-transactions", response_model=list[UserTransaction])
@limiter.limit("60/minute")
async def list_user_transactions(
    request: Request,
    symbol: str | None = None,
    limit: int = 50,
    repo: UserTransactionRepository = Depends(get_user_tx_repo),
) -> list[UserTransaction]:
    """Return user-entered transactions newest first."""
    return await repo.list_recent(symbol=symbol, limit=limit)


@router.post(
    "/user-transactions",
    response_model=UserTransaction,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("60/minute")
async def create_user_transaction(
    request: Request,
    payload: UserTransactionCreate,
    repo: UserTransactionRepository = Depends(get_user_tx_repo),
    holding_repo: HoldingRepository = Depends(get_holding_repository),
) -> UserTransaction:
    """Record a new user-entered buy/sell. Auto-syncs holdings collection."""
    tx = await repo.create(payload)
    try:
        await apply_transaction(tx, holding_repo, sign=1)
    except (OversellError, NoHoldingToSellError) as e:
        # Roll back the transaction so we don't have an orphan
        await repo.delete(tx.transaction_id)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        await repo.delete(tx.transaction_id)
        logger.error("tx_holding_apply_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply transaction to holdings: {e}",
        ) from e
    return tx


@router.patch("/user-transactions/{transaction_id}", response_model=UserTransaction)
@limiter.limit("60/minute")
async def update_user_transaction(
    request: Request,
    transaction_id: str,
    payload: UserTransactionUpdate,
    repo: UserTransactionRepository = Depends(get_user_tx_repo),
    holding_repo: HoldingRepository = Depends(get_holding_repository),
) -> UserTransaction:
    """Edit an existing transaction. Reverse-applies the old version, then forward-applies the new."""
    if (
        payload.quantity is None
        and payload.price is None
        and payload.total_amount is None
        and payload.executed_at is None
        and payload.notes is None
    ):
        raise HTTPException(
            status_code=422, detail="At least one field must be provided"
        )

    old = await repo.get(transaction_id)
    if old is None:
        raise HTTPException(
            status_code=404, detail=f"Transaction {transaction_id} not found"
        )

    # Reverse old → update DB → forward new. If forward fails, restore.
    try:
        await apply_transaction(old, holding_repo, sign=-1)
    except (OversellError, NoHoldingToSellError) as e:
        # Already-edited holdings somewhere have made the old tx un-reversible
        raise HTTPException(
            status_code=409,
            detail=f"Cannot edit: holdings state changed since this tx ({e})",
        ) from e

    new = await repo.update(transaction_id, payload)
    if new is None:
        # Re-apply old as best-effort restore
        await apply_transaction(old, holding_repo, sign=1)
        raise HTTPException(status_code=404, detail="Transaction vanished mid-edit")

    try:
        await apply_transaction(new, holding_repo, sign=1)
    except (OversellError, NoHoldingToSellError) as e:
        # Restore: revert to old in both places
        await apply_transaction(new, holding_repo, sign=-1)
        await repo.update(
            transaction_id,
            UserTransactionUpdate(
                quantity=old.quantity,
                price=old.price,
                total_amount=old.total_amount,
                executed_at=old.executed_at,
                notes=old.notes,
            ),
        )
        await apply_transaction(old, holding_repo, sign=1)
        raise HTTPException(status_code=400, detail=str(e)) from e
    return new


@router.delete(
    "/user-transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT
)
@limiter.limit("60/minute")
async def delete_user_transaction(
    request: Request,
    transaction_id: str,
    repo: UserTransactionRepository = Depends(get_user_tx_repo),
    holding_repo: HoldingRepository = Depends(get_holding_repository),
) -> None:
    """Delete a transaction and reverse its effect on holdings."""
    tx = await repo.get(transaction_id)
    if tx is None:
        raise HTTPException(
            status_code=404, detail=f"Transaction {transaction_id} not found"
        )
    try:
        await apply_transaction(tx, holding_repo, sign=-1)
    except (OversellError, NoHoldingToSellError) as e:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: would leave holdings inconsistent ({e})",
        ) from e
    await repo.delete(transaction_id)
