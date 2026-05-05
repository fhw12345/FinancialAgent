"""
Two new top-level analysis flows for the dashboard buttons:

- run_analyze_holdings: full Phase 1 (ReAct + 118 MCP tools per symbol) on
  every holding, then Phase 2 holistic decisions. Persists decisions to
  portfolio_orders with recommendation_source="holdings" + full per-symbol
  research embedded in metadata.full_research.
- run_today_picks: sector-filtered universe → top 20 finalists (cap for
  runtime) → full Phase 1 per finalist → Phase 2 picks Top 5 BUYs. Same
  recommendation_source="picks" tagging.

Both flows write a single aggregated summary chat message at the end so
the user can see the run on their chat list, but skip the per-symbol chat
churn that the cron-driven analyze_user_portfolio creates.

If `app.state.portfolio_agent` is missing (init failed at startup), both
flows fall back to the simplified single-LLM-call path via
_phase2_for_symbols (preserves v0.15.0 behavior).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from ...core.utils.date_utils import utcnow
from ...database.repositories.holding_repository import HoldingRepository
from ...database.repositories.message_repository import MessageRepository
from ...database.repositories.portfolio_order_repository import (
    PortfolioOrderRepository,
)
from ...models.message import MessageCreate, MessageMetadata
from ...models.portfolio import PortfolioOrder
from ...models.portfolio_analysis import PortfolioSettings
from .context_builder import build_context_from_mongo
from .universe_filter import filter_by_risk

logger = structlog.get_logger(__name__)

# Picks Phase 1 cap — 20 symbols × ~30-90s/symbol = ~5-15min including
# concurrency. Above this the user wait is unreasonable.
PICKS_PHASE1_CAP = 20


@dataclass
class _SymbolStub:
    """Duck-typed object satisfying Phase 1's `.symbol` access on positions/watchlist."""

    symbol: str


def _resolve_data_manager(app: Any) -> Any:
    return getattr(getattr(app, "state", None), "data_manager", None)


def _resolve_mongo(app: Any) -> Any:
    """Pull the MongoDB instance off app.state if present."""
    state = getattr(app, "state", None)
    return getattr(state, "mongodb", None) if state else None


def _resolve_portfolio_agent(app: Any) -> Any:
    """Pull the PortfolioAnalysisAgent singleton off app.state if available."""
    return getattr(getattr(app, "state", None), "portfolio_agent", None)


# ---------------------------------------------------------------------------
# Flow A: Analyze My Holdings
# ---------------------------------------------------------------------------


async def run_analyze_holdings(app: Any, settings: PortfolioSettings) -> dict[str, Any]:
    """
    Full Phase 1+2 pipeline on existing positions; persist decisions tagged 'holdings'.
    """
    mongo = _resolve_mongo(app)
    dm = _resolve_data_manager(app)
    pa = _resolve_portfolio_agent(app)
    if mongo is None or dm is None:
        raise RuntimeError("app.state.mongodb / data_manager missing")

    redis_cache = app.state.redis
    holding_repo = HoldingRepository(mongo.get_collection("holdings"))
    order_repo = PortfolioOrderRepository(mongo.get_collection("portfolio_orders"))
    message_repo = MessageRepository(mongo.get_collection("messages"), redis_cache)

    holdings = await holding_repo.list_by_user()
    if not holdings:
        return {"message": "Add holdings first", "result_count": 0}

    context = await build_context_from_mongo(settings, holding_repo, dm)
    symbols = [h.symbol for h in holdings]

    # If the full pipeline is unavailable, fall back to single-LLM shortcut.
    if pa is None:
        logger.warning("portfolio_agent_unavailable_using_simplified")
        decisions = await _phase2_for_symbols(
            symbols=symbols, context=context, settings=settings, flow_label="holdings"
        )
        written = await _persist_decisions(
            decisions,
            dm,
            order_repo,
            source="holdings",
            run_id=f"holdings_{uuid.uuid4().hex[:8]}",
        )
        return {
            "message": f"[fallback] Analyzed {len(symbols)} holding(s); persisted {written}.",
            "result_count": written,
        }

    # ---- Full pipeline path ----
    run_id = f"holdings_{uuid.uuid4().hex[:8]}"
    positions = [_SymbolStub(symbol=s) for s in symbols]
    summary: dict[str, Any] = {
        "holdings_analyzed": 0,
        "watchlist_analyzed": 0,
        "errors": [],
    }
    logger.info("holdings_full_pipeline_start", run_id=run_id, count=len(positions))
    phase1_results = await pa._run_phase1_research(
        positions=positions,
        watchlist_items=[],
        user_id="local",
        dry_run=False,
        result_summary=summary,
        suppress_chat=True,
    )
    research_by_symbol = {r.symbol: r.analysis_text for r in phase1_results}
    if not phase1_results:
        return {
            "message": "Phase 1 produced no research (all symbols failed).",
            "result_count": 0,
        }
    _, trading_decisions = await pa._run_phase2_decisions(
        all_analysis_results=phase1_results,
        portfolio_context=context,
        user_id="local",
        dry_run=False,
    )
    decisions = _trading_decisions_to_dicts(trading_decisions)
    written = await _persist_decisions(
        decisions,
        dm,
        order_repo,
        source="holdings",
        run_id=run_id,
        research_by_symbol=research_by_symbol,
    )
    await _write_summary_chat(message_repo, "holdings", run_id, decisions)
    return {
        "message": f"Researched {len(phase1_results)} holding(s); persisted {written} decision(s).",
        "result_count": written,
    }


# ---------------------------------------------------------------------------
# Flow B: Today's Picks
# ---------------------------------------------------------------------------


async def run_today_picks(
    app: Any, settings: PortfolioSettings, sectors: list[str]
) -> dict[str, Any]:
    """
    Full pipeline: sector filter → top 20 finalists (cap) → Phase 1 per
    symbol → Phase 2 → Top 5 BUYs. Tagged recommendation_source='picks'.
    """
    mongo = _resolve_mongo(app)
    dm = _resolve_data_manager(app)
    pa = _resolve_portfolio_agent(app)
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
        return {"message": "No symbols match selected sectors.", "result_count": 0}

    finalists = await filter_by_risk(candidates, settings.risk_tolerance, dm)
    if not finalists:
        return {"message": "Universe filter returned 0 finalists.", "result_count": 0}

    # Cap Phase 1 universe — 50 finalists × 30-90s would be 25-75 minutes.
    finalists = finalists[:PICKS_PHASE1_CAP]

    order_repo = PortfolioOrderRepository(mongo.get_collection("portfolio_orders"))
    message_repo = MessageRepository(mongo.get_collection("messages"), app.state.redis)

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
    if pa is None:
        logger.warning("portfolio_agent_unavailable_using_simplified")
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
        return {
            "message": f"[fallback] Analyzed {len(symbols)} candidate(s); persisted {written}.",
            "result_count": written,
        }

    # ---- Full pipeline path ----
    run_id = f"picks_{uuid.uuid4().hex[:8]}"
    watchlist_stubs = [_SymbolStub(symbol=s) for s in symbols]
    summary: dict[str, Any] = {
        "holdings_analyzed": 0,
        "watchlist_analyzed": 0,
        "errors": [],
    }
    logger.info("picks_full_pipeline_start", run_id=run_id, count=len(watchlist_stubs))
    phase1_results = await pa._run_phase1_research(
        positions=[],
        watchlist_items=watchlist_stubs,
        user_id="local",
        dry_run=False,
        result_summary=summary,
        suppress_chat=True,
    )
    research_by_symbol = {r.symbol: r.analysis_text for r in phase1_results}
    if not phase1_results:
        return {
            "message": "Phase 1 produced no research (all candidates failed).",
            "result_count": 0,
        }
    _, trading_decisions = await pa._run_phase2_decisions(
        all_analysis_results=phase1_results,
        portfolio_context=context,
        user_id="local",
        dry_run=False,
    )
    # Picks: only keep BUY recommendations, capped at Top 5 by confidence
    buys = [
        d
        for d in _trading_decisions_to_dicts(trading_decisions)
        if d["decision"].lower() == "buy"
    ]
    buys.sort(key=lambda d: d.get("confidence") or 0, reverse=True)
    top5 = buys[:5]
    written = await _persist_decisions(
        top5,
        dm,
        order_repo,
        source="picks",
        run_id=run_id,
        research_by_symbol=research_by_symbol,
    )
    await _write_summary_chat(message_repo, "picks", run_id, top5)
    msg = (
        f"Researched {len(phase1_results)} candidate(s); persisted {written} pick(s)."
        if written
        else f"Researched {len(phase1_results)} candidate(s); none met BUY criteria."
    )
    return {"message": msg, "result_count": written}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _trading_decisions_to_dicts(trading_decisions: list[Any]) -> list[dict[str, Any]]:
    """Normalize Phase 2 TradingDecision objects to the dict shape _persist_decisions wants."""
    out = []
    for d in trading_decisions or []:
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
    return out


async def _write_summary_chat(
    message_repo: MessageRepository,
    flow: str,
    run_id: str,
    decisions: list[dict[str, Any]],
) -> None:
    """One aggregated summary message per run — keeps the chat list clean."""
    date_str = utcnow().strftime("%Y-%m-%d")
    chat_id = f"system-run-{flow}-{date_str}"
    title = "Holdings Analysis" if flow == "holdings" else "Today's Picks"
    if decisions:
        lines = [
            f"- **{d['symbol']}** {d['decision'].upper()}"
            f" (conf {d.get('confidence', '?')}/10)"
            f" — {d.get('reasoning_summary', '')[:160]}"
            for d in decisions
        ]
        body = "\n".join(lines)
        content = (
            f"### {title} — {date_str}\n"
            f"_run id: `{run_id}`_\n\n"
            f"{body}\n\n"
            f"_Click any decision row in the dashboard to see the full per-symbol research._"
        )
    else:
        content = (
            f"### {title} — {date_str}\n"
            f"_run id: `{run_id}`_\n\n"
            f"No actionable decisions produced this run."
        )
    try:
        await message_repo.create(
            MessageCreate(
                chat_id=chat_id,
                role="assistant",
                content=content,
                source="llm",
                metadata=MessageMetadata(
                    analysis_id=run_id, analysis_type="portfolio_run_summary"
                ),
            )
        )
    except Exception as e:
        logger.warning("summary_chat_write_failed", run_id=run_id, error=str(e))


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
    research_by_symbol: dict[str, str] | None = None,
) -> int:
    """Write each decision as a PortfolioOrder row tagged with source + run_id.

    If `research_by_symbol` is provided, the per-symbol Phase 1 research text
    is embedded into `metadata.full_research` so the dashboard can show it.
    """
    research_by_symbol = research_by_symbol or {}
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
                "full_research": research_by_symbol.get(sym, ""),
            },
        )
        try:
            await order_repo.create(row)
            written += 1
        except Exception as e:
            logger.warning("decision_persist_failed", symbol=sym, error=str(e))
    return written
