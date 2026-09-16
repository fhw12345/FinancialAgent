"""Research-first dashboard flows. Stage A persists assessments, never new orders."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from ...database.repositories.holding_repository import HoldingRepository
from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ...models.portfolio_analysis import PortfolioSettings
from ...services.decision_policy.context import current_run_id
from .consistency_gate import run_consistency_gate
from .context_builder import build_context_from_mongo
from .decision_persistence import (
    _persist_decisions,
    _trading_decisions_to_dicts,
)
from .decision_persistence import _phase2_for_symbols as _phase2_for_symbols
from .universe_filter import filter_by_risk

logger = structlog.get_logger(__name__)
PICKS_PHASE1_CAP = 20


@dataclass
class _SymbolStub:
    symbol: str


def _resolve_data_manager(app: Any) -> Any:
    return getattr(getattr(app, "state", None), "data_manager", None)


def _resolve_mongo(app: Any) -> Any:
    return getattr(getattr(app, "state", None), "mongodb", None)


def _resolve_portfolio_agent(app: Any) -> Any:
    return getattr(getattr(app, "state", None), "portfolio_agent", None)


async def _apply_consistency_gate(phase1_results: list[Any]) -> None:
    """A check error is explicit unavailability; cancellation still propagates."""

    async def one(result: Any) -> None:
        try:
            verdict, degraded = await run_consistency_gate(
                result.symbol, result.analysis_text or ""
            )
            result.consistency_passed = verdict.passed and verdict.available
            result.consistency_violations = [
                {"field": v.field, "quote": v.quote} for v in verdict.violations
            ]
            if not verdict.available:
                result.consistency_violations.append(
                    {
                        "field": "consistency_check",
                        "quote": "",
                        "code": "CHECK_UNAVAILABLE",
                    }
                )
            result.degraded_fields = degraded
            result.prompt_versions.update(verdict.prompt_versions)
        except Exception as error:
            result.consistency_passed = False
            result.consistency_violations = [
                {"field": "consistency_check", "quote": "", "code": "CHECK_UNAVAILABLE"}
            ]
            logger.warning(
                "consistency_check_unavailable",
                symbol=result.symbol,
                error_type=type(error).__name__,
            )

    await asyncio.gather(*(one(result) for result in phase1_results))


def _build_data_quality_map(phase1_results: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        r.symbol: {
            "degraded_fields": list(getattr(r, "degraded_fields", []) or []),
            "consistency_violations": list(
                getattr(r, "consistency_violations", []) or []
            ),
            "consistency_passed": getattr(r, "consistency_passed", None),
            "check_unavailable": getattr(r, "consistency_passed", None) is None,
        }
        for r in phase1_results
    }


async def _research_and_assess(
    app: Any,
    settings: PortfolioSettings | None,
    symbols: list[str],
    context: dict[str, Any],
    source: str,
    *,
    as_holdings: bool,
) -> dict[str, Any]:
    mongo, dm, pa = (
        _resolve_mongo(app),
        _resolve_data_manager(app),
        _resolve_portfolio_agent(app),
    )
    if mongo is None or dm is None:
        raise RuntimeError("MongoDB/DataManager unavailable")
    symbols = list(dict.fromkeys(s.upper() for s in symbols))
    run_id = current_run_id() or f"{source}_{uuid.uuid4().hex}"
    repository = PortfolioOrderRepository(mongo.get_collection("portfolio_orders"))
    summary: dict[str, Any] = {
        "holdings_analyzed": 0,
        "watchlist_analyzed": 0,
        "errors": [],
    }
    results: list[Any] = []
    if pa is not None:
        stubs = [_SymbolStub(symbol=s) for s in symbols]
        results = await pa._run_phase1_research(
            positions=stubs if as_holdings else [],
            watchlist_items=[] if as_holdings else stubs,
            user_id="local",
            dry_run=False,
            result_summary=summary,
            suppress_chat=True,
        )
        await _apply_consistency_gate(results)
    # The absent-agent path never invokes _phase2_for_symbols or another model.
    research = {r.symbol: r.analysis_text for r in results}
    quality = _build_data_quality_map(results)
    for symbol in symbols:
        if symbol not in research:
            quality[symbol] = {"check_unavailable": True}
    complete = len(results) == len(symbols) and {r.symbol for r in results} == set(
        symbols
    )
    checked = complete and all(
        r.consistency_passed is True and not r.degraded_fields for r in results
    )
    if current_run_id():
        canonical = await mongo.get_collection("agent_runs").find_one(
            {"run_id": run_id}
        )
        # Do not launch another model phase after an observed stop/failure.
        checked = (
            checked and canonical is not None and canonical.get("status") == "running"
        )
    proposals: list[dict[str, Any]] = []
    if checked and pa is not None:
        decision_result, decisions = await pa._run_phase2_decisions(
            all_analysis_results=results,
            portfolio_context=context,
            user_id="local",
            dry_run=False,
            flow=source,
        )
        proposals = _trading_decisions_to_dicts(decisions)
        if decision_result is None:
            for symbol in symbols:
                quality[symbol]["decision_unavailable"] = True
    held = (
        [p["symbol"] for p in context.get("positions", [])]
        if settings is not None and source != "picks"
        else None
    )
    written = await _persist_decisions(
        proposals,
        dm,
        repository,
        source=source,
        run_id=run_id,
        research_by_symbol=research,
        data_quality_by_symbol=quality,
        redis_cache=app.state.redis,
        expected_symbols=symbols,
        holdings=held,
    )
    return {
        "message": f"Stage A: saved {written} non-actionable research assessment(s). No trade recommendation is approved.",
        "result_count": written,
        "assessment_count": written,
        "actionable_count": 0,
        "run_id": run_id,
    }


async def run_analyze_holdings(app: Any, settings: PortfolioSettings) -> dict[str, Any]:
    mongo, dm = _resolve_mongo(app), _resolve_data_manager(app)
    if mongo is None or dm is None:
        raise RuntimeError("MongoDB/DataManager unavailable")
    repo = HoldingRepository(mongo.get_collection("holdings"))
    holdings = await repo.list_by_user()
    if not holdings:
        return {
            "message": "Add holdings first",
            "result_count": 0,
            "actionable_count": 0,
        }
    context = await build_context_from_mongo(settings, repo, dm)
    return await _research_and_assess(
        app,
        settings,
        [h.symbol for h in holdings],
        context,
        "holdings",
        as_holdings=True,
    )


async def run_single_symbol(
    app: Any, symbol: str, settings: PortfolioSettings | None = None
) -> dict[str, Any]:
    mongo, dm = _resolve_mongo(app), _resolve_data_manager(app)
    if mongo is None or dm is None:
        raise RuntimeError("MongoDB/DataManager unavailable")
    sym = symbol.strip().upper()
    if not sym or not sym.replace(".", "").isalnum() or len(sym) > 10:
        raise ValueError("Invalid requested symbol")
    repo = HoldingRepository(mongo.get_collection("holdings"))
    context = (
        await build_context_from_mongo(settings, repo, dm)
        if settings is not None
        else {"positions": [], "cash": 0.0, "total_equity": 0.0, "buying_power": 0.0}
    )
    result = await _research_and_assess(
        app, settings, [sym], context, "single_symbol", as_holdings=False
    )
    return {**result, "symbol": sym}


async def run_today_picks(
    app: Any, settings: PortfolioSettings, sectors: list[str]
) -> dict[str, Any]:
    if not sectors:
        return {
            "message": "No sectors selected — pick at least one.",
            "result_count": 0,
            "actionable_count": 0,
        }
    from ...data.sector_universe import filter_universe

    candidates = filter_universe(sectors)
    if not candidates:
        return {
            "message": "No symbols match selected sectors.",
            "result_count": 0,
            "actionable_count": 0,
        }
    finalists = (
        await filter_by_risk(
            candidates, settings.risk_tolerance, _resolve_data_manager(app)
        )
    )[:PICKS_PHASE1_CAP]
    if not finalists:
        return {
            "message": "Universe filter returned 0 finalists.",
            "result_count": 0,
            "actionable_count": 0,
        }
    context = {
        "total_equity": settings.cash_balance,
        "buying_power": settings.cash_balance,
        "cash": settings.cash_balance,
        "positions": [],
        "risk_tolerance": settings.risk_tolerance,
        "max_position_pct": settings.max_position_pct,
        "mode": "today_picks_top5",
    }
    return await _research_and_assess(
        app,
        settings,
        [r.symbol for r in finalists],
        context,
        "picks",
        as_holdings=False,
    )
