"""
Portfolio holdings and summary endpoints.

W5a: Alpaca live trading removed. Holdings & summary are now derived from the
local ``holdings`` MongoDB collection (or empty when none exist) instead of
querying a broker account.
"""

import structlog
from fastapi import APIRouter, Depends, Request

from ...database.repositories.holding_repository import HoldingRepository
from ..dependencies.portfolio_deps import get_holding_repository
from ..dependencies.rate_limit import limiter
from ..schemas.portfolio_models import (
    HoldingResponse,
    PortfolioSummaryResponse,
)

logger = structlog.get_logger()

router = APIRouter()


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
        (total_unrealized_pl / total_cost_basis * 100.0) if total_cost_basis > 0 else 0.0
    )

    return PortfolioSummaryResponse(
        holdings_count=len(holdings),
        total_cost_basis=total_cost_basis,
        total_market_value=total_market_value,
        total_unrealized_pl=total_unrealized_pl,
        total_unrealized_pl_pct=total_unrealized_pl_pct,
    )
