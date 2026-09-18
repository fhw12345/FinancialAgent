"""Research composition over sealed evidence; persistence failures never imply success."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from ...database.repositories.evidence_repository import (
    EvidenceRepository,
    EvidenceStorage,
)
from ...models.evidence import EvidenceSnapshot, EvidenceSummary
from ...models.portfolio_risk import PortfolioRiskSnapshot
from ...models.research_strategy import StrategyVersion
from ...services.decision_policy.context import current_run_id
from ...services.portfolio_risk import service as risk_service
from .claims import build_dossier
from .collection import collect
from .context import evidence_scope


async def prepare(
    db: EvidenceStorage,
    dm: Any,
    market: Any,
    symbols: list[str],
    run_id: str,
    risk: PortfolioRiskSnapshot,
    strategy: StrategyVersion | None = None,
) -> dict[str, EvidenceSnapshot]:
    repository = EvidenceRepository(db)
    run = await db.get_collection("agent_runs").find_one({"run_id": run_id})
    as_of = run.get("started_at") if run else risk.captured_at
    if not isinstance(as_of, datetime):
        as_of = risk.captured_at
    as_of = as_of.replace(tzinfo=UTC) if as_of.tzinfo is None else as_of.astimezone(UTC)
    from .identity import digest

    peer_symbols = strategy.parameters.peer_symbols if strategy else []
    peer_ids = {s: "snapshot_" + digest([run_id, "research", s]) for s in peer_symbols}
    semaphore = asyncio.Semaphore(2)

    async def one(symbol: str) -> EvidenceSnapshot:
        async with semaphore:
            return await collect(
                repository,
                request_key="research",
                run_id=run_id,
                symbol=symbol,
                as_of=as_of,
                data_manager=dm,
                market_service=market,
                risk=risk,
                strategy=strategy,
                peers={
                    s: identifier for s, identifier in peer_ids.items() if s != symbol
                },
            )

    snapshots = await asyncio.gather(
        *(one(s) for s in sorted(set(symbols) | set(peer_symbols)))
    )
    return {s.symbol: s for s in snapshots if s.symbol in symbols}


async def dossiers(
    db: EvidenceStorage,
    snapshots: dict[str, EvidenceSnapshot],
    research: dict[str, str],
) -> EvidenceSummary:
    repository = EvidenceRepository(db)
    ids = []
    errors = []
    for symbol, snapshot in sorted(snapshots.items()):
        dossier = build_dossier(snapshot, research.get(symbol, ""))
        await repository.save_dossier(dossier)
        ids.append(dossier.dossier_id)
        errors.extend(dossier.errors)
    return EvidenceSummary(
        snapshot_ids=[s.snapshot_id for _, s in sorted(snapshots.items())],
        dossier_ids=ids,
        errors=sorted(set(errors)),
    )


async def run_deep(
    agent: Any, workflow: Any, state: Any, config: Any, symbol: str
) -> dict[str, Any]:
    if agent._order_repo is None or agent._data_manager is None:
        raise RuntimeError("Deep evidence storage/providers are unavailable")
    db = agent._order_repo.collection.database
    run_id = current_run_id()
    if run_id is None:
        raise RuntimeError("Deep evidence requires a canonical run identity")
    from ..research_strategy import service as strategy_service
    from ..research_strategy import store
    from ..research_strategy.context import strategy_scope

    strategy = await store.active(db)
    risk = await risk_service.capture(
        db, sorted({symbol} | set(strategy.parameters.peer_symbols if strategy else []))
    )
    snapshots = await prepare(
        db,
        agent._data_manager,
        agent._data_manager._av_service,
        [symbol],
        run_id,
        risk,
        strategy=strategy,
    )
    strategy_reviews = await strategy_service.reviews(db, snapshots)
    with evidence_scope(snapshots), strategy_scope(strategy_reviews):
        result = dict(await workflow.ainvoke(state, config=config))
    await strategy_service.record_prompts(db, run_id, strategy_reviews)
    result["strategy_summary"] = strategy_service.summary(strategy_reviews)
    report = str(result.get("research_report") or "")
    summary = await dossiers(db, snapshots, {symbol: report})
    result["evidence_summary"] = summary.model_dump(mode="json")
    return result


async def deep_summary(
    db: EvidenceStorage, run_id: str, symbol: str, report: str
) -> EvidenceSummary:
    from .identity import digest

    repository = EvidenceRepository(db)
    snapshot = await repository.get("snapshot_" + digest([run_id, "research", symbol]))
    return await dossiers(db, {symbol: snapshot}, {symbol: report})
