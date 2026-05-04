"""
Repository for user_transactions collection.
Hard-deletes; updated_at bumped on each write.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from src.core.utils.date_utils import utcnow

from ...models.user_transaction import (
    UserTransaction,
    UserTransactionCreate,
    UserTransactionUpdate,
)

logger = structlog.get_logger()


class UserTransactionRepository:
    """CRUD for user_transactions."""

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def ensure_indexes(self) -> None:
        await self.collection.create_index(
            [("executed_at", -1)], name="idx_executed_at"
        )
        await self.collection.create_index([("symbol", 1)], name="idx_symbol")
        await self.collection.create_index(
            [("transaction_id", 1)], name="idx_tx_id", unique=True
        )

    async def create(self, payload: UserTransactionCreate) -> UserTransaction:
        now = utcnow()
        total = (
            payload.total_amount
            if payload.total_amount is not None
            else round(payload.quantity * payload.price, 4)
        )
        tx = UserTransaction(
            transaction_id=f"tx_{uuid.uuid4().hex[:12]}",
            symbol=payload.symbol.upper(),
            side=payload.side,
            quantity=payload.quantity,
            price=payload.price,
            total_amount=total,
            executed_at=payload.executed_at or now,
            notes=payload.notes,
            created_at=now,
            updated_at=now,
        )
        await self.collection.insert_one(tx.model_dump())
        logger.info(
            "user_transaction_created",
            transaction_id=tx.transaction_id,
            symbol=tx.symbol,
            side=tx.side,
            quantity=tx.quantity,
        )
        return tx

    async def get(self, transaction_id: str) -> UserTransaction | None:
        doc = await self.collection.find_one({"transaction_id": transaction_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return UserTransaction(**doc)

    async def list_recent(
        self, symbol: str | None = None, limit: int = 50
    ) -> list[UserTransaction]:
        q: dict[str, Any] = {}
        if symbol:
            q["symbol"] = symbol.upper()
        cursor = self.collection.find(q).sort("executed_at", -1).limit(limit)
        out: list[UserTransaction] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(UserTransaction(**doc))
        return out

    async def update(
        self, transaction_id: str, payload: UserTransactionUpdate
    ) -> UserTransaction | None:
        update: dict[str, Any] = {"updated_at": utcnow()}
        if payload.quantity is not None:
            update["quantity"] = payload.quantity
        if payload.price is not None:
            update["price"] = payload.price
        if payload.total_amount is not None:
            update["total_amount"] = payload.total_amount
        if payload.executed_at is not None:
            update["executed_at"] = payload.executed_at
        if payload.notes is not None:
            update["notes"] = payload.notes

        # Auto-recompute total if either qty or price changed but total wasn't given
        if payload.total_amount is None and (
            payload.quantity is not None or payload.price is not None
        ):
            current = await self.get(transaction_id)
            if current:
                new_qty = (
                    payload.quantity
                    if payload.quantity is not None
                    else current.quantity
                )
                new_price = (
                    payload.price if payload.price is not None else current.price
                )
                update["total_amount"] = round(new_qty * new_price, 4)

        result = await self.collection.find_one_and_update(
            {"transaction_id": transaction_id},
            {"$set": update},
            return_document=True,
        )
        if not result:
            return None
        result.pop("_id", None)
        return UserTransaction(**result)

    async def delete(self, transaction_id: str) -> bool:
        r = await self.collection.delete_one({"transaction_id": transaction_id})
        return r.deleted_count > 0

    async def delete_by_symbol(self, symbol: str) -> int:
        r = await self.collection.delete_many({"symbol": symbol.upper()})
        return r.deleted_count
