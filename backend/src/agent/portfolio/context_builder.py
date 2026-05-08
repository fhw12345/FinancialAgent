"""
Build a portfolio_context dict from Mongo holdings + user-set cash settings.

Replaces the Alpaca path in agent.py:266 when trading_service is None.
Schema-compatible with what Phase 2 expects:
    {
        "total_equity": float,
        "buying_power": float,
        "cash": float,
        "positions": [
            {symbol, quantity, market_value, unrealized_pl_percent}, ...
        ],
    }
"""

from __future__ import annotations

from typing import Any

import structlog

from ...database.repositories.holding_repository import HoldingRepository
from ...models.portfolio_analysis import PortfolioSettings

logger = structlog.get_logger(__name__)


async def build_context_from_mongo(
    settings: PortfolioSettings,
    holding_repo: HoldingRepository,
    data_manager: Any,
) -> dict[str, Any]:
    """
    Assemble the dict Phase 2 consumes.

    Holdings without a current_price are best-effort enriched via DataManager.
    Cash comes straight from `settings.cash_balance`.
    """
    holdings = await holding_repo.list_by_user()
    positions: list[dict[str, Any]] = []
    total_market_value = 0.0

    for h in holdings:
        # Ensure we have a current price (cron may not have run yet)
        price = h.current_price or 0.0
        session = h.last_session
        if price <= 0 and data_manager is not None:
            try:
                q = await data_manager.get_quote(h.symbol)
                price = float(getattr(q, "price", 0) or 0)
                session = getattr(q, "session", None) or session
            except Exception as e:
                logger.debug("context_quote_failed", symbol=h.symbol, error=str(e))

        market_value = (h.quantity * price) if price > 0 else (h.market_value or 0)
        cost_basis = h.cost_basis or (h.quantity * h.avg_price)
        upl_pct = (
            ((market_value - cost_basis) / cost_basis * 100.0)
            if cost_basis > 0 and market_value > 0
            else 0.0
        )

        positions.append(
            {
                "symbol": h.symbol,
                "quantity": int(h.quantity),
                "market_value": float(market_value),
                "unrealized_pl_percent": float(upl_pct),
                "session": session,
            }
        )
        total_market_value += market_value

    total_equity = total_market_value + settings.cash_balance
    return {
        "total_equity": float(total_equity),
        "buying_power": float(settings.cash_balance),
        "cash": float(settings.cash_balance),
        "positions": positions,
        # Surface risk knobs so Phase 2 can use them
        "risk_tolerance": settings.risk_tolerance,
        "max_position_pct": settings.max_position_pct,
    }
