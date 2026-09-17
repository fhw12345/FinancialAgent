"""Every important claim rejection stays explicit, including non-finite and derived inputs."""

from datetime import UTC, datetime, timedelta
import json
import pytest
from src.models.evidence import EvidenceRecord, ResearchClaim
from src.services.evidence.claims import validate_claim, build_dossier
from tests.test_evidence_claims import record, snapshot, claim, NOW


@pytest.mark.parametrize(
    "change",
    [
        {"value": None},
        {"unit": "unknown"},
        {"published_at": None, "document_id": None, "point_in_time_status": "verified"},
        {"fetched_at": datetime(2026, 9, 17)},
        {
            "period_start": datetime(2026, 9, 18).date(),
            "period_end": datetime(2026, 9, 16).date(),
        },
        {"value": float("inf")},
    ],
)
def test_invalid_records_do_not_qualify_as_available(change):
    with pytest.raises(ValueError):
        record(**change)


@pytest.mark.parametrize("kind", ["hypothesis", "judgment"])
def test_numbers_in_subjective_claims_remain_unverified(kind):
    result = validate_claim(snapshot(), claim(kind=kind))
    assert (
        result.status == "unverified"
        and "NUMERIC_JUDGMENT_UNVERIFIED" in result.reasons
    )


def test_missing_unknown_period_future_observation_and_alias_are_rejected():
    r = record(quality="missing", value=None, period="unknown", legacy_aliases=["old"])
    result = validate_claim(snapshot([r]), claim(r, evidence_ids=[]))
    assert "EVIDENCE_REQUIRED" in result.reasons
    result = validate_claim(snapshot([r]), claim(r))
    assert {"EVIDENCE_MISSING", "PERIOD_UNVERIFIED"} <= set(result.reasons)
    assert (
        "LEGACY_ALIAS_UNRESOLVED"
        in validate_claim(snapshot([r]), claim(r, evidence_ids=["old"])).reasons
    )
    r = record(
        observed_at=NOW + timedelta(minutes=1),
        period_end=(NOW + timedelta(days=1)).date(),
    )
    result = validate_claim(snapshot([r]), claim(r))
    assert {
        "OBSERVATION_AFTER_CUTOFF",
        "ECONOMIC_PERIOD_AFTER_CUTOFF",
        "STALE_SESSION",
    } <= set(result.reasons)
    s = snapshot()
    s.state = "collecting"
    assert "SNAPSHOT_NOT_SEALED" in validate_claim(s, claim()).reasons
    assert (
        "FACT_METHOD_NOT_ALLOWED"
        in validate_claim(snapshot(), claim(method="net_margin@1")).reasons
    )


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"metric": "revenue"}, "CALCULATOR_INPUT_MISMATCH"),
        ({"method": None}, "CALCULATOR_INPUT_MISMATCH"),
        ({"unit": "USD"}, "UNIT_MISMATCH"),
        ({"value": 0.8}, "VALUE_MISMATCH"),
    ],
)
def test_derived_claims_validate_registered_contract(change, reason):
    a = record(metric="net_income", value=20)
    b = record(metric="revenue", value=100)
    c = claim(
        a,
        kind="derived",
        metric="net_margin",
        value=0.2,
        unit="ratio",
        method="net_margin@1",
        evidence_ids=[a.evidence_id, b.evidence_id],
    )
    assert validate_claim(snapshot([a, b]), c).status == "matches_snapshot"
    assert (
        reason in validate_claim(snapshot([a, b]), c.model_copy(update=change)).reasons
    )


def test_zero_denominator_negative_capex_and_wrong_input_units_fail():
    a = record(metric="net_income", value=20)
    b = record(metric="revenue", value=0)
    c = claim(
        a,
        kind="derived",
        metric="net_margin",
        value=0.0,
        unit="ratio",
        method="net_margin@1",
        evidence_ids=[a.evidence_id, b.evidence_id],
    )
    assert "ZERO_DENOMINATOR" in validate_claim(snapshot([a, b]), c).reasons
    a = record(metric="operating_cash_flow", value=100)
    b = record(metric="capital_expenditure", value=-20)
    c = claim(
        a,
        kind="derived",
        metric="free_cash_flow",
        value=120,
        method="free_cash_flow@1",
        evidence_ids=[a.evidence_id, b.evidence_id],
    )
    assert "CAPEX_SIGN_UNSUPPORTED" in validate_claim(snapshot([a, b]), c).reasons
    b = record(metric="capital_expenditure", unit="shares", value=20)
    c.evidence_ids = [a.evidence_id, b.evidence_id]
    assert "CALCULATOR_UNIT_MISMATCH" in validate_claim(snapshot([a, b]), c).reasons


def test_model_cannot_forge_authority_or_turn_malformed_claims_into_a_pass():
    for content in [
        "",
        '<claims-json>{"claims":[]}</claims-json>',
        '<claims-json>{"claims":{},"verified":true}</claims-json>',
    ]:
        assert "CLAIMS_MISSING_OR_INVALID" in build_dossier(snapshot(), content).errors
    with pytest.raises(ValueError):
        ResearchClaim(**claim().model_dump(), verified=True)
