"""Evidence-bound research contracts across Portfolio/Deep, without actionable side effects."""

import json
from typing import Any

from ...database.repositories.agent_run_repository import AgentRunRepository
from ...database.repositories.evidence_repository import (
    EvidenceRepository,
    EvidenceStorage,
)
from ...models.evidence import EvidenceSnapshot
from ...models.research_strategy import (
    StrategyConclusion,
    StrategyConclusions,
    StrategyReview,
    StrategySummary,
)
from ..portfolio_risk.service import policy_state
from . import context, store
from .evaluation import evaluate


async def reviews(
    db: EvidenceStorage, snapshots: dict[str, EvidenceSnapshot]
) -> dict[str, StrategyReview]:
    return {
        symbol: await evaluate(db, snapshot)
        for symbol, snapshot in sorted(snapshots.items())
        if snapshot.strategy_contract
    }


def summary(values: dict[str, StrategyReview]) -> StrategySummary | None:
    if not values:
        return None
    return StrategySummary(
        reviews=list(values.values()),
        errors=sorted({e for r in values.values() for e in r.errors}),
    )


async def record_prompts(
    db: EvidenceStorage, run_id: str, values: dict[str, StrategyReview]
) -> None:
    versions = {
        key: value for r in values.values() for key, value in r.prompt_versions.items()
    }
    if versions:
        await AgentRunRepository(db.get_collection("agent_runs")).merge_prompt_versions(
            run_id, versions
        )


def apply_conclusions(
    values: dict[str, StrategyReview],
    snapshots: dict[str, EvidenceSnapshot],
    result: StrategyConclusions,
) -> None:
    seen = set()
    for conclusion in result.conclusions:
        if conclusion.symbol not in values or conclusion.symbol in seen:
            raise ValueError("STRATEGY_CONCLUSION_SCOPE_MISMATCH")
        seen.add(conclusion.symbol)
        snapshot = snapshots[conclusion.symbol]
        conflicted = {i for ids in snapshot.conflicts.values() for i in ids}
        allowed = {
            r.evidence_id
            for r in snapshot.records
            if r.quality == "available" and r.evidence_id not in conflicted
        }
        review = values[conclusion.symbol]
        if any(not set(t.evidence_ids) <= allowed for t in conclusion.theses):
            review.errors.append("THESIS_EVIDENCE_UNVERIFIED")
        if review.status != "research_only" and conclusion.stance != "unknown":
            review.errors.append("STANCE_WITH_INSUFFICIENT_INPUTS")
        if conclusion.stance != "unknown" and not conclusion.theses:
            review.errors.append("THESIS_REQUIRED")
        review.conclusion = conclusion
    if seen != set(values):
        for symbol in set(values) - seen:
            values[symbol].errors.append("CONCLUSION_MISSING")


async def conclude(
    agent: Any, analyses: list[Any], snapshots: dict[str, EvidenceSnapshot]
) -> tuple[StrategyConclusions, list[Any]]:
    from ...agent.prompt_registry import get_prompt

    values = context.current()
    spec = get_prompt("strategy-conclusion")
    for review in values.values():
        review.prompt_versions[spec.prompt_id] = spec.versioned_id
    prompt = spec.render(
        reviews=json.dumps(
            [r.model_dump(mode="json") for r in values.values()], ensure_ascii=False
        ),
        research="\n".join(str(a.analysis_text) for a in analyses),
    )
    raw = await agent.ainvoke_structured(
        prompt=prompt, schema=StrategyConclusions, context=None
    )
    result = StrategyConclusions.model_validate(raw)
    apply_conclusions(values, snapshots, result)
    return result, []


async def project(db: EvidenceStorage, value: StrategySummary) -> StrategySummary:
    active = await store.active(db)
    costs = await policy_state(db)
    result = value.model_copy(deep=True)
    for review in result.reviews:
        review.stale = (
            active is None
            or active.version_id != review.contract.version_id
            or costs.revision != review.contract.cost_policy_revision
        )
    return result


async def saved_deep_summary(
    db: EvidenceStorage, run_id: str, symbol: str, verdict: StrategyConclusion
) -> StrategySummary:
    from ..evidence.identity import digest

    snapshot = await EvidenceRepository(db).get(
        "snapshot_" + digest([run_id, "research", symbol])
    )
    values = await reviews(db, {symbol: snapshot})
    apply_conclusions(
        values, {symbol: snapshot}, StrategyConclusions(conclusions=[verdict])
    )
    for review in values.values():
        review.prompt_versions = {
            "strategy-fundamental": "strategy-fundamental@1",
            "strategy-conclusion": "strategy-conclusion@1",
        }
    result = summary(values)
    if result is None:
        raise ValueError("STRATEGY_SNAPSHOT_REQUIRED")
    return result
