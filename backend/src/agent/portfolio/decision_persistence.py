"""Assessment-only persistence for portfolio flows; no PortfolioOrder construction."""

from typing import Any

from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ...models.portfolio_risk import PortfolioRiskReview
from ...services.decision_policy.context import current_run_id


def _trading_decisions_to_dicts(trading_decisions: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for d in trading_decisions or []:
        if hasattr(d, "model_dump"):
            rows.append(d.model_dump(mode="json"))
        elif isinstance(d, dict):
            rows.append(dict(d))
        else:
            rows.append(
                {
                    "symbol": getattr(d, "symbol", "UNKNOWN"),
                    "decision": str(getattr(d, "decision", "")),
                    "intent": getattr(d, "intent", None),
                    "position_size_percent": getattr(d, "position_size_percent", None),
                    "entry_price": getattr(d, "entry_price", None),
                    "stop_loss": getattr(d, "stop_loss", None),
                    "take_profit": getattr(d, "take_profit", None),
                    "reasoning_summary": getattr(d, "reasoning_summary", ""),
                }
            )
    return rows


async def _persist_decisions(
    decisions: list[dict[str, Any]],
    data_manager: Any,
    order_repo: PortfolioOrderRepository,
    source: str,
    run_id: str,
    research_by_symbol: dict[str, str] | None = None,
    data_quality_by_symbol: dict[str, dict[str, Any]] | None = None,
    redis_cache: Any = None,
    *,
    expected_symbols: list[str],
    holdings: list[str] | None = None,
    portfolio_risk: PortfolioRiskReview | None = None,
) -> int:
    quotes: dict[str, float | None] = {}
    for symbol in expected_symbols:
        if portfolio_risk:
            quotes[symbol] = next(
                (a.mark for a in portfolio_risk.snapshot.assets if a.symbol == symbol),
                None,
            )
            continue
        try:
            quote = await data_manager.get_quote(symbol)
            quotes[symbol] = float(getattr(quote, "price", 0) or 0)
        except Exception:
            quotes[symbol] = None
    canonical = current_run_id()
    batch = await order_repo.assess(
        request_key=canonical or run_id,
        run_id=canonical,
        source=source,
        symbols=expected_symbols,
        proposals=decisions,
        research=research_by_symbol,
        quality=data_quality_by_symbol,
        quotes=quotes,
        holdings=holdings,
        portfolio_risk=portfolio_risk,
    )
    return len(batch.results)


async def _phase2_for_symbols(**kwargs: Any) -> list[dict[str, Any]]:
    """Compatibility name: an unavailable research pipeline is NOT an LLM shortcut."""
    raise RuntimeError("Stage A: evidence-free recommendation fallback is disabled")
