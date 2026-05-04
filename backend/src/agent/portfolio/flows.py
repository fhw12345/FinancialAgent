"""
Two new top-level analysis flows for the dashboard buttons:

- run_analyze_holdings: LLM analyzes user's existing positions, writes
  decisions to portfolio_orders with recommendation_source="holdings"
- run_today_picks: LLM picks Top 5 BUYs from sector-filtered S&P/Nasdaq
  universe (NOT from holdings), writes with recommendation_source="picks"

Both share Phase 2 LLM logic but differ in the symbol universe and
decision_type tagging. Both short-circuit cleanly when there's nothing
to analyze (empty holdings / empty sector intersection).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from ...core.utils.date_utils import utcnow
from ...database.repositories.holding_repository import HoldingRepository
from ...database.repositories.portfolio_order_repository import (
    PortfolioOrderRepository,
)
from ...models.portfolio import PortfolioOrder
from ...models.portfolio_analysis import PortfolioSettings
from .context_builder import build_context_from_mongo
from .universe_filter import filter_by_risk

logger = structlog.get_logger(__name__)


def _resolve_data_manager(app: Any) -> Any:
    return getattr(getattr(app, "state", None), "data_manager", None)


def _resolve_mongo(app: Any) -> Any:
    """Pull the MongoDB instance off app.state if present."""
    state = getattr(app, "state", None)
    return getattr(state, "mongodb", None) if state else None


# ---------------------------------------------------------------------------
# Flow A: Analyze My Holdings
# ---------------------------------------------------------------------------


async def run_analyze_holdings(app: Any, settings: PortfolioSettings) -> dict[str, Any]:
    """LLM-analyze existing positions; persist decisions tagged 'holdings'."""
    mongo = _resolve_mongo(app)
    dm = _resolve_data_manager(app)
    if mongo is None or dm is None:
        raise RuntimeError("app.state.mongodb / data_manager missing")

    holding_repo = HoldingRepository(mongo.get_collection("holdings"))
    order_repo = PortfolioOrderRepository(mongo.get_collection("portfolio_orders"))

    holdings = await holding_repo.list_by_user()
    if not holdings:
        return {"message": "Add holdings first", "result_count": 0}

    context = await build_context_from_mongo(settings, holding_repo, dm)
    symbols = [h.symbol for h in holdings]

    # Lazy imports to avoid circular dependencies at module load
    decisions = await _phase2_for_symbols(
        symbols=symbols,
        context=context,
        settings=settings,
        flow_label="holdings",
    )
    written = await _persist_decisions(
        decisions,
        dm,
        order_repo,
        source="holdings",
        run_id=f"holdings_{uuid.uuid4().hex[:8]}",
    )
    return {
        "message": f"Analyzed {len(symbols)} holding(s); persisted {written} decision(s).",
        "result_count": written,
    }


# ---------------------------------------------------------------------------
# Flow B: Today's Picks
# ---------------------------------------------------------------------------


async def run_today_picks(
    app: Any, settings: PortfolioSettings, sectors: list[str]
) -> dict[str, Any]:
    """Sector-filtered Top 5 BUY recommendations from S&P/Nasdaq universe."""
    mongo = _resolve_mongo(app)
    dm = _resolve_data_manager(app)
    if mongo is None or dm is None:
        raise RuntimeError("app.state.mongodb / data_manager missing")

    if not sectors:
        return {
            "message": "No sectors selected — pick at least one.",
            "result_count": 0,
        }

    from ...data.sector_universe import filter_universe

    candidates = filter_universe(sectors)
    if not candidates:
        return {
            "message": "No symbols match selected sectors.",
            "result_count": 0,
        }

    finalists = await filter_by_risk(candidates, settings.risk_tolerance, dm)
    if not finalists:
        return {"message": "Universe filter returned 0 finalists.", "result_count": 0}

    holding_repo = HoldingRepository(mongo.get_collection("holdings"))
    order_repo = PortfolioOrderRepository(mongo.get_collection("portfolio_orders"))

    # Build a "context" that says no current positions — this is fresh-pick mode
    context = {
        "total_equity": settings.cash_balance,
        "buying_power": settings.cash_balance,
        "cash": settings.cash_balance,
        "positions": [],
        "risk_tolerance": settings.risk_tolerance,
        "max_position_pct": settings.max_position_pct,
        "mode": "today_picks_top5",
    }

    symbols = [r.symbol for r in finalists]
    decisions = await _phase2_for_symbols(
        symbols=symbols,
        context=context,
        settings=settings,
        flow_label="picks",
        top_n=5,
    )
    written = await _persist_decisions(
        decisions,
        dm,
        order_repo,
        source="picks",
        run_id=f"picks_{uuid.uuid4().hex[:8]}",
    )
    msg = (
        f"Analyzed {len(symbols)} candidate(s); persisted {written} pick(s)."
        if written
        else "No candidates met BUY criteria today."
    )
    return {"message": msg, "result_count": written}


# ---------------------------------------------------------------------------
# Shared Phase 2 wrapper + persistence
# ---------------------------------------------------------------------------


async def _phase2_for_symbols(
    symbols: list[str],
    context: dict[str, Any],
    settings: PortfolioSettings,
    flow_label: str,
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """
    Direct LLM call producing structured decisions for a symbol list.

    This is a deliberately simpler path than the full Phase 1→2 pipeline
    in PortfolioAnalysisAgent — for the two-button UX we want:
    - holdings flow: one decision per existing position
    - picks flow:    Top N (5) BUYs from candidate list, or none

    Reuses the cross-vendor llm_factory + the structured-output schema
    from models.trading_decision.
    """
    from langchain_core.messages import HumanMessage

    from ...models.trading_decision import PortfolioDecisionList
    from ..llm_factory import get_llm

    if not symbols:
        return []

    llm = get_llm("portfolio_decisions", temperature=0.4, max_tokens=4000, timeout=120)
    structured = llm.with_structured_output(schema=PortfolioDecisionList)

    risk_line = (
        f"Risk tolerance: {settings.risk_tolerance}. "
        f"Max single position: {settings.max_position_pct}% of cash."
    )
    cash_line = f"Available cash: ${settings.cash_balance:,.0f}."
    pos_block = (
        "Current positions:\n"
        + "\n".join(
            f"- {p['symbol']}: {p['quantity']} shares, mv=${p['market_value']:.0f}, upl={p['unrealized_pl_percent']:+.1f}%"
            for p in context.get("positions", [])
        )
        if context.get("positions")
        else "Current positions: NONE."
    )

    if flow_label == "holdings":
        instruction = (
            f"Analyze the user's CURRENT POSITIONS below and decide BUY (add), "
            f"SELL (trim/exit), or HOLD for each one. Return one TradingDecision "
            f"per symbol in the same order: {', '.join(symbols)}. "
            f"Stay within max position cap and respect risk tier."
        )
    else:
        topn = top_n or 5
        instruction = (
            f"From the CANDIDATE list below, pick the {topn} most attractive BUY ideas "
            f"for today given the user's cash and risk profile. Return at most {topn} "
            f"TradingDecision items, all with decision=BUY. If NO candidate is "
            f"attractive, return an empty list. Candidates: {', '.join(symbols)}."
        )

    prompt = (
        f"You are a senior portfolio manager.\n\n"
        f"{risk_line}\n{cash_line}\n\n{pos_block}\n\n{instruction}"
    )
    logger.info("phase2_call", flow=flow_label, symbols_count=len(symbols))

    try:
        result = await structured.ainvoke([HumanMessage(content=prompt)])
    except Exception as e:
        logger.error("phase2_llm_failed", flow=flow_label, error=str(e))
        return []

    out: list[dict[str, Any]] = []
    for d in getattr(result, "decisions", []) or []:
        out.append(
            {
                "symbol": d.symbol,
                "decision": (
                    d.decision.value
                    if hasattr(d.decision, "value")
                    else str(d.decision)
                ),
                "position_size_percent": d.position_size_percent,
                "confidence": d.confidence,
                "reasoning_summary": d.reasoning_summary,
            }
        )
    if top_n:
        out = out[:top_n]
    return out


async def _persist_decisions(
    decisions: list[dict[str, Any]],
    data_manager: Any,
    order_repo: PortfolioOrderRepository,
    source: str,
    run_id: str,
) -> int:
    """Write each decision as a PortfolioOrder row tagged with source + run_id."""
    written = 0
    for d in decisions:
        sym = d["symbol"].upper()
        action = d["decision"].lower()
        if action not in ("buy", "sell", "hold"):
            continue
        side = action  # match PortfolioOrder.side semantics
        # Resolve decision_price (anchor for ex-post P&L)
        try:
            q = await data_manager.get_quote(sym)
            decision_price = float(getattr(q, "price", 0) or 0)
        except Exception:
            decision_price = 0.0
        if decision_price <= 0:
            logger.warning("decision_skipped_no_price", symbol=sym)
            continue

        decision_type = "order" if action != "hold" else "signal"
        row = PortfolioOrder(
            order_id=f"{source}_{uuid.uuid4().hex[:12]}",
            chat_id=f"{source}_flow",
            user_id="local",
            message_id=None,
            alpaca_order_id=None,
            analysis_id=run_id,
            symbol=sym,
            order_type="market",
            side=side,
            quantity=0.0,  # we don't translate position_size_percent → shares here
            limit_price=None,
            stop_price=None,
            time_in_force="day",
            status="signal" if decision_type == "signal" else "suggested",
            filled_qty=0.0,
            filled_avg_price=None,
            filled_at=None,
            error_message=None,
            created_at=utcnow(),
            decision_price=decision_price,
            decision_type=decision_type,
            recommendation_source=source,
            metadata={
                "confidence": d.get("confidence"),
                "position_size_percent": d.get("position_size_percent"),
                "reasoning": d.get("reasoning_summary", "")[:500],
            },
        )
        try:
            await order_repo.create(row)
            written += 1
        except Exception as e:
            logger.warning("decision_persist_failed", symbol=sym, error=str(e))
    return written
