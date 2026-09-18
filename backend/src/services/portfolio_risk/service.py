"""Capture immutable account/market inputs and versioned preview policy; never mutate holdings."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Protocol

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...core.exceptions import AppError
from ...database.repositories.holding_repository import HoldingRepository
from ...models.portfolio_risk import (
    AllocationReceipt,
    PolicyState,
    PortfolioRiskReview,
    PortfolioRiskSnapshot,
    RiskAsset,
    RiskPolicy,
    RiskPosition,
    TargetProposal,
)
from ..decision_policy.control import service_write
from . import provider
from .allocation import allocate
from .calendar import completed_session
from .estimator import estimate


class MongoDB(Protocol):
    def get_collection(self, name: str) -> Any: ...


class RiskConflict(AppError):
    status_code = 409
    error_type = "risk_revision_changed"


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


async def account(mongo: MongoDB) -> tuple[list[RiskPosition], float | None, str]:
    rows = await HoldingRepository(mongo.get_collection("holdings")).list_by_user()
    settings = await mongo.get_collection("user_settings").find_one({}) or {}
    positions = sorted(
        [
            RiskPosition(symbol=h.symbol, quantity=h.quantity, cost_basis=h.cost_basis)
            for h in rows
        ],
        key=lambda p: p.symbol,
    )
    cash = settings.get("cash_balance")
    if cash is not None:
        if isinstance(cash, bool) or not isinstance(cash, (int, float)):
            raise ValueError("Invalid cash balance")
        cash = float(cash)
        if cash < 0:
            raise ValueError("Negative cash is unsupported")
    revision = digest(
        {"positions": [p.model_dump(mode="json") for p in positions], "cash": cash}
    )
    return positions, cash, revision


async def policy_state(mongo: MongoDB) -> PolicyState:
    row = await mongo.get_collection("risk_policy").find_one({"_id": "local"})
    if row is None:
        return PolicyState()
    row.pop("_id", None)
    return PolicyState.model_validate(row)


@service_write
async def confirm_policy(
    mongo: MongoDB, policy: RiskPolicy, expected: int
) -> PolicyState:
    state = PolicyState(
        policy=policy, revision=expected + 1, confirmed_at=datetime.now(UTC)
    )
    try:
        row = await mongo.get_collection("risk_policy").find_one_and_update(
            {"_id": "local", "revision": expected},
            {"$set": state.model_dump(mode="json")},
            upsert=expected == 0,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as error:
        raise RiskConflict("Risk policy changed; reload before confirming") from error
    if row is None:
        raise RiskConflict("Risk policy changed; reload before confirming")
    row.pop("_id", None)
    return PolicyState.model_validate(row)


async def capture(
    mongo: MongoDB, symbols: list[str] | None = None
) -> PortfolioRiskSnapshot:
    positions, cash, revision = await account(mongo)
    policy = await policy_state(mongo)
    now = datetime.now(UTC)
    session = completed_session(now)
    semaphore = asyncio.Semaphore(4)

    async def fetch(symbol: str) -> RiskAsset:
        async with semaphore:
            return await provider.fetch_asset(symbol, session)

    assets = await asyncio.gather(
        *(fetch(s) for s in sorted({p.symbol for p in positions} | set(symbols or [])))
    )
    _, _, after = await account(mongo)
    after_policy = await policy_state(mongo)
    errors = []
    if revision != after:
        errors.append("ACCOUNT_CHANGED_DURING_CAPTURE")
    if policy.revision != after_policy.revision:
        errors.append("POLICY_CHANGED_DURING_CAPTURE")
    snapshot = PortfolioRiskSnapshot(
        account_revision=revision,
        captured_at=now,
        session_date=session,
        cash=cash,
        positions=positions,
        assets=assets,
        policy=policy,
        errors=errors,
    )
    snapshot.snapshot_id = "risk_" + digest(snapshot.model_dump(mode="json"))
    return snapshot


async def review_current(mongo: MongoDB) -> PortfolioRiskReview:
    snapshot = await capture(mongo)
    review = PortfolioRiskReview(snapshot=snapshot, current=estimate(snapshot))
    await mongo.get_collection("portfolio_risk_captures").create_index(
        [("snapshot.captured_at", -1)]
    )
    row = await mongo.get_collection("portfolio_risk_captures").find_one_and_update(
        {"_id": snapshot.snapshot_id},
        {"$setOnInsert": review.model_dump(mode="json")},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if row is None:
        raise RuntimeError("Risk capture persistence returned no record")
    return review


async def project_stale(
    mongo: MongoDB, review: PortfolioRiskReview
) -> PortfolioRiskReview:
    _, _, revision = await account(mongo)
    policy = await policy_state(mongo)
    reasons = []
    if revision != review.snapshot.account_revision:
        reasons.append("ACCOUNT_CHANGED")
    if policy.revision != review.snapshot.policy.revision:
        reasons.append("POLICY_CHANGED")
    if completed_session(datetime.now(UTC)) != review.snapshot.session_date:
        reasons.append("SESSION_CHANGED")
    return review.model_copy(update={"stale": bool(reasons), "stale_reasons": reasons})


async def latest(mongo: MongoDB) -> PortfolioRiskReview | None:
    row = await mongo.get_collection("portfolio_risk_captures").find_one(
        {}, sort=[("snapshot.captured_at", -1)]
    )
    if row is None:
        return None
    row.pop("_id", None)
    return await project_stale(mongo, PortfolioRiskReview.model_validate(row))


def assess_drafts(
    snapshot: PortfolioRiskSnapshot, drafts: list[dict[str, Any]]
) -> PortfolioRiskReview:
    """Explicitly translate the legacy model size basis; confidence is never a sizing input."""
    current = estimate(snapshot)
    proposals = []
    failures = []
    positions = {p.symbol: p for p in snapshot.positions}
    assets = {a.symbol: a for a in snapshot.assets}
    for draft in drafts:
        symbol = str(draft.get("symbol", ""))
        asset = assets.get(symbol)
        if asset is None or asset.mark is None or not current.equity:
            failures.append("PROPOSAL_MARK_UNAVAILABLE:" + symbol)
            continue
        value = (
            (positions[symbol].quantity * asset.mark) if symbol in positions else 0.0
        )
        size = draft.get("position_size_percent")
        action = draft.get("decision")
        if action == "HOLD":
            target = value / current.equity
        elif (
            isinstance(size, bool)
            or not isinstance(size, (int, float))
            or not 0 < size <= 100
        ):
            failures.append("INVALID_MODEL_SIZE:" + symbol)
            continue
        elif action == "BUY":
            target = (value + (snapshot.cash or 0) * size / 100) / current.equity
        elif action == "SELL" and symbol in positions:
            target = value * (1 - size / 100) / current.equity
        else:
            failures.append("UNSUPPORTED_ACTION_OR_EXPOSURE:" + symbol)
            continue
        if not 0 <= target <= 1:
            failures.append("INVALID_TARGET_WEIGHT:" + symbol)
            continue
        proposals.append(
            TargetProposal(
                symbol=symbol,
                target_weight=target,
                stop=draft.get("stop_loss") if action == "BUY" else None,
            )
        )
    allocation = (
        AllocationReceipt(status="blocked", constraints=sorted(set(failures)))
        if failures
        else allocate(snapshot, proposals)
    )
    allocation.allocation_id = "allocation_" + digest(
        {
            "snapshot": snapshot.snapshot_id,
            "receipt": allocation.model_dump(mode="json"),
        }
    )
    return PortfolioRiskReview(
        snapshot=snapshot, current=current, allocation=allocation
    )


def prompt_context(snapshot: PortfolioRiskSnapshot) -> dict[str, Any]:
    risk = estimate(snapshot)
    assets = {a.symbol: a for a in snapshot.assets}
    return {
        "total_equity": risk.equity or 0.0,
        "cash": snapshot.cash or 0.0,
        "buying_power": snapshot.cash or 0.0,
        "positions": [
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "market_value": p.quantity * (assets[p.symbol].mark or 0),
                "unrealized_pl_percent": (
                    (p.quantity * (assets[p.symbol].mark or 0) - p.cost_basis)
                    / p.cost_basis
                    * 100
                    if p.cost_basis > 0
                    else 0.0
                ),
                "session": "closed",
            }
            for p in snapshot.positions
        ],
        "risk_snapshot": snapshot.model_dump(mode="json"),
    }
