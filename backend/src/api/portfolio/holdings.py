"""
Portfolio holdings and summary endpoints.

W5a: Alpaca live trading removed. Holdings & summary are now derived from the
local ``holdings`` MongoDB collection (or empty when none exist) instead of
querying a broker account.

W6 (decision-tracking): added POST/PATCH/DELETE for direct holdings management.
"""

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from ...database.repositories.holding_repository import HoldingRepository
from ...database.repositories.user_transaction_repository import (
    UserTransactionRepository,
)
from ...models.holding import Holding, HoldingCreate, HoldingUpdate
from ..dependencies.portfolio_deps import get_holding_repository
from ..dependencies.rate_limit import limiter
from ..schemas.portfolio_models import (
    HoldingResponse,
    PortfolioSummaryResponse,
)
from .user_transactions import get_user_tx_repo

logger = structlog.get_logger()

router = APIRouter()

# Wrap quote fetch with a hard timeout so a slow vendor never blocks POST.
QUOTE_TIMEOUT_SECONDS = 3.0


@router.get("/holdings", response_model=list[HoldingResponse])
@limiter.limit("30/minute")
async def get_holdings(
    request: Request,
    holding_repo: HoldingRepository = Depends(get_holding_repository),
) -> list[HoldingResponse]:
    """List portfolio holdings from local MongoDB (broker integration removed)."""
    holdings = await holding_repo.list_by_user()
    logger.info("Holdings retrieved from MongoDB", count=len(holdings))
    return [HoldingResponse.from_holding(h) for h in holdings]


@router.get("/summary", response_model=PortfolioSummaryResponse)
@limiter.limit("30/minute")
async def get_portfolio_summary(
    request: Request,
    holding_repo: HoldingRepository = Depends(get_holding_repository),
) -> PortfolioSummaryResponse:
    """Aggregate portfolio summary from local holdings (broker integration removed)."""
    holdings = await holding_repo.list_by_user()

    total_cost_basis = sum(h.cost_basis or 0.0 for h in holdings)
    total_market_value = sum(h.market_value or 0.0 for h in holdings)
    total_unrealized_pl = total_market_value - total_cost_basis
    total_unrealized_pl_pct = (
        (total_unrealized_pl / total_cost_basis * 100.0)
        if total_cost_basis > 0
        else 0.0
    )

    return PortfolioSummaryResponse(
        holdings_count=len(holdings),
        total_cost_basis=total_cost_basis,
        total_market_value=total_market_value,
        total_unrealized_pl=total_unrealized_pl,
        total_unrealized_pl_pct=total_unrealized_pl_pct,
    )


# ---------------------------------------------------------------------------
# Mutations: POST / PATCH / DELETE
# ---------------------------------------------------------------------------


async def _enrich_with_quote(
    request: Request,
    holding: Holding,
    *,
    persist: bool = False,
    holding_repo: HoldingRepository | None = None,
) -> Holding:
    """Best-effort: fetch live quote via DataManager, populate live fields.

    Failures are swallowed — caller still gets the inserted holding back.
    Bounded by QUOTE_TIMEOUT_SECONDS so a slow vendor cannot block POST.

    When `persist=True` and a `holding_repo` is provided, also writes the
    fetched price back to mongo via `repo.update_price` so subsequent GETs
    show the same number (otherwise the in-memory enrichment is response-only).
    """
    dm = getattr(request.app.state, "data_manager", None)
    if dm is None:
        return holding
    try:
        quote = await asyncio.wait_for(
            dm.get_quote(holding.symbol), timeout=QUOTE_TIMEOUT_SECONDS
        )
        price = float(getattr(quote, "price", 0) or 0)
        if price <= 0:
            return holding
        session = getattr(quote, "session", None)
        holding.current_price = price
        holding.market_value = holding.quantity * price
        holding.unrealized_pl = holding.market_value - holding.cost_basis
        holding.unrealized_pl_pct = (
            (holding.unrealized_pl / holding.cost_basis * 100.0)
            if holding.cost_basis > 0
            else 0.0
        )
        if session:
            holding.last_session = session
        if persist and holding_repo is not None:
            try:
                await holding_repo.update_price(
                    holding.holding_id, price, session=session
                )
            except Exception as e:
                logger.warning(
                    "holding_price_persist_failed",
                    symbol=holding.symbol,
                    error=str(e),
                )
    except (TimeoutError, Exception) as e:
        logger.warning(
            "holding_quote_enrichment_failed",
            symbol=holding.symbol,
            error=str(e),
        )
    return holding


@router.post("/holdings", response_model=HoldingResponse)
@limiter.limit("60/minute")
async def create_or_merge_holding(
    request: Request,
    payload: HoldingCreate,
    holding_repo: HoldingRepository = Depends(get_holding_repository),
) -> HoldingResponse:
    """
    Create a new holding, or merge into an existing row for the same symbol.

    Merge formula (weighted-average cost):
        new_qty = existing_qty + incoming_qty
        new_avg = (existing_qty * existing_avg + incoming_qty * incoming_avg) / new_qty

    avg_price is REQUIRED at the API layer (the model marks it optional but the
    repo crashes on None — see CHANGELOG v0.13.x). Pydantic validation enforces
    `quantity > 0` and (when present) `avg_price > 0` from the model.
    """
    if payload.avg_price is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="avg_price is required",
        )

    symbol = payload.symbol.upper()
    # RACE: read-modify-write here is not transactional. Acceptable for the
    # single-user local tool; two near-simultaneous POSTs for the same symbol
    # could both miss each other and the second one would 500 on the unique
    # index. Document and tolerate.
    existing = await holding_repo.get_by_symbol(symbol=symbol)
    if existing is not None:
        new_qty = existing.quantity + payload.quantity
        new_avg = (
            existing.quantity * existing.avg_price
            + payload.quantity * payload.avg_price
        ) / new_qty
        merged = await holding_repo.update(
            existing.holding_id,
            HoldingUpdate(quantity=new_qty, avg_price=new_avg),
        )
        if merged is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Merge update returned no row",
            )
        merged = await _enrich_with_quote(
            request, merged, persist=True, holding_repo=holding_repo
        )
        logger.info(
            "Holding merged",
            symbol=symbol,
            new_quantity=new_qty,
            new_avg_price=round(new_avg, 4),
        )
        return HoldingResponse.from_holding(merged)

    # New row
    payload_with_upper = HoldingCreate(
        symbol=symbol, quantity=payload.quantity, avg_price=payload.avg_price
    )
    created = await holding_repo.create(holding_create=payload_with_upper)
    created = await _enrich_with_quote(
        request, created, persist=True, holding_repo=holding_repo
    )
    return HoldingResponse.from_holding(created)


@router.patch("/holdings/{holding_id}", response_model=HoldingResponse)
@limiter.limit("60/minute")
async def update_holding(
    request: Request,
    holding_id: str,
    payload: HoldingUpdate,
    holding_repo: HoldingRepository = Depends(get_holding_repository),
) -> HoldingResponse:
    """Partial update — quantity and/or avg_price. cost_basis recalcs in repo."""
    if payload.quantity is None and payload.avg_price is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of quantity, avg_price required",
        )
    updated = await holding_repo.update(holding_id, payload)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holding {holding_id} not found",
        )
    updated = await _enrich_with_quote(
        request, updated, persist=True, holding_repo=holding_repo
    )
    return HoldingResponse.from_holding(updated)


@router.delete("/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
async def delete_holding(
    request: Request,
    holding_id: str,
    holding_repo: HoldingRepository = Depends(get_holding_repository),
    tx_repo: UserTransactionRepository = Depends(get_user_tx_repo),
) -> None:
    """Hard delete — cascades to user_transactions for the same symbol to keep
    the ledger and holdings collection from drifting apart."""
    holding = await holding_repo.get(holding_id)
    if holding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holding {holding_id} not found",
        )
    removed_tx = await tx_repo.delete_by_symbol(holding.symbol)
    ok = await holding_repo.delete(holding_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Holding {holding_id} not found",
        )
    logger.info(
        "holding_deleted_with_cascade",
        holding_id=holding_id,
        symbol=holding.symbol,
        removed_transactions=removed_tx,
    )


@router.post("/holdings/refresh-prices")
@limiter.limit("10/minute")
async def refresh_holding_prices(
    request: Request,
    holding_repo: HoldingRepository = Depends(get_holding_repository),
) -> dict:
    """Manually refresh current_price + market_value + P&L for every holding.

    Same logic as the nightly cron (`scripts/refresh_holding_prices.py`),
    but on-demand from the dashboard's [Refresh Prices] button. Each symbol
    is fetched concurrently via DataManager (Finnhub → AV → yfinance).
    """
    dm = getattr(request.app.state, "data_manager", None)
    if dm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DataManager unavailable",
        )

    holdings = await holding_repo.list_by_user()
    if not holdings:
        return {"refreshed": 0, "failed": 0, "total": 0}

    sem = asyncio.Semaphore(8)

    async def _refresh_one(h: Holding) -> bool:
        async with sem:
            try:
                quote = await asyncio.wait_for(
                    dm.get_quote(h.symbol), timeout=QUOTE_TIMEOUT_SECONDS
                )
                price = float(getattr(quote, "price", 0) or 0)
                if price <= 0:
                    return False
                await holding_repo.update_price(h.holding_id, price)
                return True
            except Exception as e:
                logger.warning(
                    "holding_price_refresh_failed", symbol=h.symbol, error=str(e)
                )
                return False

    results = await asyncio.gather(*(_refresh_one(h) for h in holdings))
    refreshed = sum(1 for r in results if r)
    failed = len(results) - refreshed
    logger.info(
        "holdings_manual_refresh_done",
        refreshed=refreshed,
        failed=failed,
        total=len(holdings),
    )
    return {"refreshed": refreshed, "failed": failed, "total": len(holdings)}
