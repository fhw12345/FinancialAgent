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

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from ...core.utils.date_utils import utcnow
from ...database.repositories.holding_repository import HoldingRepository
from ...database.repositories.portfolio_order_repository import (
    PortfolioOrderRepository,
)
from ...models.portfolio import PortfolioOrder
from ...models.portfolio_analysis import PortfolioSettings
from ...services.persistence_translator import translate_for_persistence
from .consistency_gate import (
    run_consistency_gate,
    violations_as_corrective_hint,
)
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


async def _apply_consistency_gate(phase1_results: list[Any]) -> None:
    """Run W1.10 gate per symbol; tag results with degraded fields and
    consistency violations. Mutates phase1_results in place via attribute
    set (read by Phase2 prompt assembly downstream).

    Fail-open: any per-symbol exception is logged and swallowed; the
    gate is meant to nudge quality, not block the pipeline.
    """
    if not phase1_results:
        return

    async def _one(r: Any) -> None:
        try:
            verdict, degraded = await run_consistency_gate(
                r.symbol, r.analysis_text or ""
            )
            # Annotate the result so flows / Phase2 can surface it.
            r.consistency_passed = bool(verdict.passed)
            r.consistency_violations = [
                {"field": v.field, "quote": v.quote} for v in verdict.violations
            ]
            r.degraded_fields = degraded
            if not verdict.passed:
                hint = violations_as_corrective_hint(verdict.violations)
                logger.warning(
                    "consistency_gate_violations",
                    symbol=r.symbol,
                    violation_count=len(verdict.violations),
                    degraded_count=len(degraded),
                    corrective_hint_preview=hint[:200],
                )
            elif degraded:
                logger.info(
                    "consistency_gate_clean_with_degraded",
                    symbol=r.symbol,
                    degraded_count=len(degraded),
                )
        except Exception as e:  # pragma: no cover — defensive
            logger.warning(
                "consistency_gate_apply_failed", symbol=r.symbol, error=str(e)
            )

    await asyncio.gather(*(_one(r) for r in phase1_results))


def _build_data_quality_map(
    phase1_results: list[Any],
) -> dict[str, dict[str, Any]]:
    """Translate consistency-gate annotations on phase1 results into a
    per-symbol metadata payload that gets persisted on PortfolioOrder
    and surfaced in the UI as a "数据降级" tag (W1.12)."""
    out: dict[str, dict[str, Any]] = {}
    for r in phase1_results:
        degraded = getattr(r, "degraded_fields", None) or []
        violations = getattr(r, "consistency_violations", None) or []
        passed = getattr(r, "consistency_passed", None)
        if not degraded and not violations:
            continue
        payload: dict[str, Any] = {"degraded_fields": list(degraded)}
        if violations:
            payload["consistency_violations"] = list(violations)
        if passed is not None:
            payload["consistency_passed"] = bool(passed)
        out[r.symbol] = payload
    return out


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
            redis_cache=redis_cache,
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
    # W1.10 consistency gate: catch thesis bullets that cite degraded
    # data (e.g. "cheapest of seven" while P/E was unavailable). Tags
    # phase1_results in-place; Phase2 still runs but sees the warning.
    await _apply_consistency_gate(phase1_results)
    _, trading_decisions = await pa._run_phase2_decisions(
        all_analysis_results=phase1_results,
        portfolio_context=context,
        user_id="local",
        dry_run=False,
        flow="holdings",
    )
    decisions = _trading_decisions_to_dicts(trading_decisions)
    data_quality_by_symbol = _build_data_quality_map(phase1_results)
    written = await _persist_decisions(
        decisions,
        dm,
        order_repo,
        source="holdings",
        run_id=run_id,
        research_by_symbol=research_by_symbol,
        data_quality_by_symbol=data_quality_by_symbol,
        redis_cache=redis_cache,
    )
    return {
        "message": f"Researched {len(phase1_results)} holding(s); persisted {written} decision(s).",
        "result_count": written,
    }


# ---------------------------------------------------------------------------
# Flow C: Single-symbol unified pipeline (W2.1+W2.2)
# ---------------------------------------------------------------------------


async def run_single_symbol(
    app: Any, symbol: str, settings: PortfolioSettings | None = None
) -> dict[str, Any]:
    """W2.1+W2.2: route a single-symbol analysis through the same
    Phase1 + Phase2 pipeline as holdings, with Phase2 in degenerate
    single-symbol mode (no cross-position constraints).

    Why a separate flow vs. extending run_analyze_holdings:
      - Caller already knows the symbol; we don't need a holdings table.
      - Phase2 still runs so the symbol gets the same schema (intent,
        valuation, scenarios, derivations) — eliminates the
        "individual ReAct emits unstructured markdown / portfolio
        ReAct emits structured PortfolioOrder" path divergence the
        sell-side reviewer flagged.
      - Watchlist's legacy AnalysisEngine.analyze_symbol stays put for
        now; consumers that want the structured output point at this
        flow explicitly. W2.4 A/B will guide the cutover.
    """
    mongo = _resolve_mongo(app)
    dm = _resolve_data_manager(app)
    pa = _resolve_portfolio_agent(app)
    if mongo is None or dm is None or pa is None:
        raise RuntimeError("app.state.mongodb / data_manager / portfolio_agent missing")

    sym = symbol.strip().upper()
    if not sym or not sym.replace(".", "").isalnum() or len(sym) > 10:
        raise ValueError(f"invalid symbol: {symbol!r}")

    redis_cache = app.state.redis
    holding_repo = HoldingRepository(mongo.get_collection("holdings"))
    order_repo = PortfolioOrderRepository(mongo.get_collection("portfolio_orders"))

    # Pull current portfolio context if settings present (so risk_calc
    # knows existing positions); otherwise build a degenerate one.
    if settings is not None:
        context = await build_context_from_mongo(settings, holding_repo, dm)
    else:
        context = {
            "total_equity": 0.0,
            "buying_power": 0.0,
            "cash": 0.0,
            "positions": [],
            "risk_tolerance": "moderate",
            "max_position_pct": 10,
        }

    run_id = f"single_{uuid.uuid4().hex[:8]}"
    summary: dict[str, Any] = {
        "holdings_analyzed": 0,
        "watchlist_analyzed": 0,
        "errors": [],
    }
    logger.info("single_symbol_pipeline_start", run_id=run_id, symbol=sym)

    # Phase1 — single-symbol research via the watchlist branch (Phase1
    # treats symbols generically; positions vs. watchlist tags it as
    # "holding" vs "watchlist" but the research output is the same shape).
    phase1_results = await pa._run_phase1_research(
        positions=[],
        watchlist_items=[_SymbolStub(symbol=sym)],
        user_id="local",
        dry_run=False,
        result_summary=summary,
        suppress_chat=True,
    )
    if not phase1_results:
        return {
            "message": f"Phase 1 produced no research for {sym}.",
            "result_count": 0,
            "symbol": sym,
        }

    await _apply_consistency_gate(phase1_results)

    # Phase2 in degenerate single-symbol mode — same prompt path,
    # just one symbol in the list. risk_calculator block will still
    # render against the user's existing portfolio context, so the LLM
    # sees how the candidate fits.
    _, trading_decisions = await pa._run_phase2_decisions(
        all_analysis_results=phase1_results,
        portfolio_context=context,
        user_id="local",
        dry_run=False,
        flow="single_symbol",
    )

    decisions = _trading_decisions_to_dicts(trading_decisions)
    data_quality_by_symbol = _build_data_quality_map(phase1_results)
    research_by_symbol = {r.symbol: r.analysis_text for r in phase1_results}
    written = await _persist_decisions(
        decisions,
        dm,
        order_repo,
        source="single_symbol",
        run_id=run_id,
        research_by_symbol=research_by_symbol,
        data_quality_by_symbol=data_quality_by_symbol,
        redis_cache=redis_cache,
    )
    return {
        "message": f"Single-symbol Phase1+Phase2 for {sym}; persisted {written} decision(s).",
        "result_count": written,
        "symbol": sym,
        "run_id": run_id,
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
            redis_cache=app.state.redis,
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
    await _apply_consistency_gate(phase1_results)
    _, trading_decisions = await pa._run_phase2_decisions(
        all_analysis_results=phase1_results,
        portfolio_context=context,
        user_id="local",
        dry_run=False,
        flow="picks",
    )
    # Picks: only keep BUY recommendations, capped at Top 5 by confidence
    buys = [
        d
        for d in _trading_decisions_to_dicts(trading_decisions)
        if d["decision"].lower() == "buy"
    ]
    buys.sort(key=lambda d: d.get("confidence") or 0, reverse=True)
    top5 = buys[:5]
    data_quality_by_symbol = _build_data_quality_map(phase1_results)
    written = await _persist_decisions(
        top5,
        dm,
        order_repo,
        source="picks",
        run_id=run_id,
        research_by_symbol=research_by_symbol,
        data_quality_by_symbol=data_quality_by_symbol,
        redis_cache=app.state.redis,
    )
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
        # W2.11: pass through optional structured research blocks +
        # numeric derivations + intent so _persist_decisions can write
        # them under metadata.research / metadata.derivations and the
        # DecisionTracker UI can render them.
        def _dump(obj: Any) -> Any:
            if obj is None:
                return None
            if hasattr(obj, "model_dump"):
                return obj.model_dump(mode="json")
            if isinstance(obj, list):
                return [_dump(x) for x in obj]
            return obj

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
                "entry_price": getattr(d, "entry_price", None),
                "stop_loss": getattr(d, "stop_loss", None),
                "take_profit": getattr(d, "take_profit", None),
                "reasoning_summary": d.reasoning_summary,
                "intent": (
                    d.intent.value
                    if getattr(d, "intent", None) and hasattr(d.intent, "value")
                    else None
                ),
                # W2.7+ research blocks
                "thesis": getattr(d, "thesis", None),
                "valuation": _dump(getattr(d, "valuation", None)),
                "price_target": _dump(getattr(d, "price_target", None)),
                "scenarios": _dump(getattr(d, "scenarios", None)),
                "catalysts": _dump(getattr(d, "catalysts", None)),
                "risks": getattr(d, "risks", None),
                # W2.9 derivations
                "entry_derivation": _dump(getattr(d, "entry_derivation", None)),
                "stop_derivation": _dump(getattr(d, "stop_derivation", None)),
                "target_derivation": _dump(getattr(d, "target_derivation", None)),
                "size_derivation": _dump(getattr(d, "size_derivation", None)),
            }
        )
    return out


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
    data_quality_by_symbol: dict[str, dict[str, Any]] | None = None,
    redis_cache: Any = None,
) -> int:
    """Write each decision as a PortfolioOrder row tagged with source + run_id.

    If `research_by_symbol` is provided, the per-symbol Phase 1 research text
    is embedded into `metadata.full_research` so the dashboard can show it.

    If `redis_cache` is provided, both `reasoning_summary` and the much-larger
    `full_research` are pre-translated to `metadata.reasoning_zh` /
    `metadata.full_research_zh` so the DecisionTracker UI can render Chinese
    immediately instead of triggering a live `/api/translate` LLM call per
    row on first view (the full-research call was ~12s for long bodies).
    """
    research_by_symbol = research_by_symbol or {}

    # Pre-translation strategy:
    # - reasoning is short (<500 chars) → batch all of them in one LLM call
    # - full_research is long (multi-KB markdown) → translate one symbol at a
    #   time, in parallel. A single batch with multiple long markdown bodies
    #   risks exceeding max_tokens (4096) and/or breaking the JSON-array
    #   parser if any body contains unescaped quotes. Per-symbol calls also
    #   isolate failures: one symbol's translation failing shouldn't poison
    #   the rest.
    reasoning_zh_by_symbol: dict[str, str | None] = {}
    research_zh_by_symbol: dict[str, str | None] = {}
    if redis_cache is not None:
        reasoning_to_translate: dict[str, str] = {}
        research_symbols_to_translate: list[tuple[str, str]] = []
        for d in decisions:
            sym = d["symbol"].upper()
            reasoning_text = (d.get("reasoning_summary") or "")[:1000]
            if reasoning_text.strip():
                reasoning_to_translate[sym] = reasoning_text
            research_text = research_by_symbol.get(sym, "")
            if research_text.strip():
                research_symbols_to_translate.append((sym, research_text))

        if reasoning_to_translate:
            try:
                translations = await translate_for_persistence(
                    reasoning_to_translate, redis_cache=redis_cache
                )
                for sym in reasoning_to_translate:
                    reasoning_zh_by_symbol[sym] = translations.get(f"{sym}_zh")
            except Exception as e:
                logger.warning("reasoning_pretranslate_failed", error=str(e))

        if research_symbols_to_translate:
            # Parallel per-symbol translation. Each call is ~10-15s; run all
            # symbols concurrently so the wall-clock cost is the slowest
            # single translation, not their sum.
            async def _translate_one(sym: str, text: str) -> tuple[str, str | None]:
                try:
                    out = await translate_for_persistence(
                        {"r": text}, redis_cache=redis_cache
                    )
                    return sym, out.get("r_zh")
                except Exception as e:
                    logger.warning(
                        "research_pretranslate_failed", symbol=sym, error=str(e)
                    )
                    return sym, None

            results = await asyncio.gather(
                *(
                    _translate_one(sym, text)
                    for sym, text in research_symbols_to_translate
                ),
                return_exceptions=False,
            )
            for sym, zh in results:
                research_zh_by_symbol[sym] = zh

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
            decision_session = getattr(q, "session", None)
        except Exception:
            decision_price = 0.0
            decision_session = None
        if decision_price <= 0:
            logger.warning("decision_skipped_no_price", symbol=sym)
            continue

        decision_type = "order" if action != "hold" else "signal"
        # Phase 2 outputs three concrete prices anchored to tool-derived
        # levels. Map them onto the existing PortfolioOrder fields:
        #   entry_price → limit_price (the limit-order price)
        #   stop_loss   → stop_price  (the protective stop)
        #   take_profit → metadata.take_profit (no native column)
        entry_price = d.get("entry_price")
        stop_loss = d.get("stop_loss")
        take_profit = d.get("take_profit")
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
            limit_price=entry_price,
            stop_price=stop_loss,
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
            intent=d.get("intent"),
            metadata={
                "confidence": d.get("confidence"),
                "position_size_percent": d.get("position_size_percent"),
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "decision_session": decision_session,
                "reasoning": d.get("reasoning_summary", "")[:1000],
                "reasoning_zh": reasoning_zh_by_symbol.get(sym),
                "full_research": research_by_symbol.get(sym, ""),
                "full_research_zh": research_zh_by_symbol.get(sym),
                # W2.11: surface the optional structured research blocks
                # + numeric derivations into mongo metadata so the
                # DecisionTracker UI (and W2-E e2e) can render them.
                # Each is None if the LLM didn't populate the field.
                "thesis": d.get("thesis"),
                "valuation": d.get("valuation"),
                "price_target": d.get("price_target"),
                "scenarios": d.get("scenarios"),
                "catalysts": d.get("catalysts"),
                "risks": d.get("risks"),
                "entry_derivation": d.get("entry_derivation"),
                "stop_derivation": d.get("stop_derivation"),
                "target_derivation": d.get("target_derivation"),
                "size_derivation": d.get("size_derivation"),
                **(
                    {"data_quality": data_quality_by_symbol.get(sym, {})}
                    if data_quality_by_symbol and data_quality_by_symbol.get(sym)
                    else {}
                ),
            },
        )
        try:
            await order_repo.create(row)
            written += 1
        except Exception as e:
            logger.warning("decision_persist_failed", symbol=sym, error=str(e))
    return written
