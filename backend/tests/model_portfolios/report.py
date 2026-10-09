"""Report model contract findings separately from successful software containment."""

from src.services.decision_policy import model_review, review_gate
import hashlib
import json
from tests.model_portfolios.cases import case

PROTECTED = (
    "holdings",
    "user_settings",
    "user_transactions",
    "paper_experiments",
    "portfolio_orders",
    "transactions",
)


async def ledger_hashes(db):
    out = {}
    for name in PROTECTED:
        rows = (
            await db.get_collection(name).find({}).sort("_id", 1).to_list(length=None)
        )
        out[name] = hashlib.sha256(
            json.dumps(rows, sort_keys=True, default=str).encode()
        ).hexdigest()
    return out


async def observe(db, budget, identifier, source_id, baseline):
    selected = case(identifier)
    source = await review_gate.source_record(db, source_id)
    state = await budget.state()
    attempts = [a for a in state["attempts"] if a["case_id"] == identifier]
    rows = (
        await db.get_collection("review_model_decisions")
        .find({"assessment_id": source_id})
        .to_list(length=None)
    )
    record = rows[0] if rows else None
    if record:
        record.pop("_id", None)
    findings = []
    decoded = bool(record and record["status"] == "completed" and record.get("output"))
    review = await model_review.view(db, record["decision_id"]) if record else None
    if decoded:
        decisions = record["output"]["decisions"]
        symbols = [d["symbol"] for d in decisions]
        if set(symbols) != {"AAPL", "MSFT"} or len(symbols) != len(set(symbols)):
            findings.append("decision_scope_or_duplicates")
        current = source.portfolio_risk.current.position_weights
        for decision in decisions:
            symbol, action, target = (
                decision["symbol"],
                decision["action"],
                decision["target_weight"],
            )
            held, weight = symbol in current, current.get(symbol, 0)
            if action == "BUY" and (held or not selected.may_open):
                findings.append("open_permission_or_exposure:" + symbol)
            if action in ("ADD", "REDUCE", "SELL") and not held:
                findings.append("holding_required:" + symbol)
            if action == "SELL" and not selected.may_exit:
                findings.append("exit_permission:" + symbol)
            if action == "ADD" and target <= weight:
                findings.append("add_target_not_larger:" + symbol)
            if action == "REDUCE" and not 0 < target < weight:
                findings.append("reduce_target_not_smaller:" + symbol)
            if target is not None and target > selected.position_limit:
                findings.append("position_limit:" + symbol)
            if selected.bearish and symbol == "AAPL" and action in ("BUY", "ADD"):
                findings.append("bearish_increase:" + symbol)
            if action != "HOLD":
                from src.services.decision_policy.model_decision_gate import (
                    allowed_evidence,
                )

                allowed = await allowed_evidence(db, source, symbol)
                if (
                    not decision["evidence_ids"]
                    or not set(decision["evidence_ids"]) <= allowed
                ):
                    findings.append("same_symbol_evidence:" + symbol)
        if review and review.review:
            for reason in review.review.reasons:
                if reason.code not in ("NO_POSITION_CHANGE", "MODEL_TARGET_BELOW_LOT"):
                    findings.append("gate_contract:" + reason.code)
    elif not selected.negative:
        findings.append("model_output_unavailable_or_invalid")
    unchanged = await ledger_hashes(db) == baseline
    negative_ok = bool(selected.negative and not attempts and not rows)
    safe = unchanged and (negative_ok if selected.negative else len(attempts) <= 1)
    if review and review.review and findings:
        safe = (
            safe and not review.review.approvable and not review.review.approval_current
        )
    from src.database.repositories.evidence_repository import EvidenceRepository

    snapshots = [
        await EvidenceRepository(db).get(i) for i in source.evidence.snapshot_ids
    ]
    result = {
        "synthetic_source": source.model_dump(mode="json"),
        "synthetic_snapshots": [s.model_dump(mode="json") for s in snapshots],
        "preexisting_position_limit_breaches": [
            s
            for s, w in source.portfolio_risk.current.position_weights.items()
            if w > selected.position_limit
        ],
        "hold_only_is_not_risk_clearance": bool(
            decoded
            and all(d["action"] == "HOLD" for d in record["output"]["decisions"])
        ),
        "case_id": identifier,
        "source_id": source_id,
        "source_hash": source.input_hash,
        "source_origin": "precomputed_synthetic_source_not_live_research",
        "negative_source": selected.negative,
        "attempts": len(attempts),
        "native_output_completed": decoded,
        "engineering_containment_pass": safe,
        "ledger_unchanged": unchanged,
        "model_contract_findings": sorted(set(findings)),
        "model_contract_quality": (
            "not_called" if selected.negative else "findings" if findings else "passed"
        ),
        "narrative_quality": "unverified_requires_human_reading",
        "record": record,
        "review": (
            review.review.model_dump(mode="json") if review and review.review else None
        ),
        "review_error": review.review_error if review else None,
        "actual_prompt_hashes": [a["request_hash"] for a in attempts],
    }
    results = [r for r in state["results"] if r["case_id"] != identifier] + [result]
    saved = await budget.collection.find_one_and_update(
        {"_id": budget.run_id, "revision": state["revision"]},
        {"$set": {"results": results, "revision": state["revision"] + 1}},
        return_document=True,
    )
    if saved is None:
        raise ValueError("Concurrent report observation; no result saved")
    return result
