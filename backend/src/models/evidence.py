"""Versioned evidence identities, sealed manifests and structured-field validation results."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .research_strategy import StrategyVersion

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Family = Literal[
    "quote",
    "ohlcv",
    "overview",
    "cash_flow",
    "balance_sheet",
    "news",
    "filing",
    "income_statement",
]
Quality = Literal["available", "stale", "missing", "conflicting", "unsupported"]
Period = Literal["instant", "session", "quarter", "annual", "ttm", "event", "unknown"]


class EvidenceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, revalidate_instances="always"
    )


class EvidenceRecord(EvidenceModel):
    evidence_id: str = ""
    snapshot_id: str
    symbol: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,14}$")
    instrument_id: str
    exchange: str | None = None
    currency: str | None = None
    family: Family
    metric: str = Field(max_length=80)
    value: Number | str | None = None
    unit: str = Field(max_length=40)
    period: Period = "unknown"
    period_start: date | None = None
    period_end: date | None = None
    observed_at: datetime | None = None
    session: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    provider: str = Field(max_length=80)
    source_uri: str | None = None
    document_id: str | None = None
    point_in_time_status: Literal["verified", "retrieval_only", "unknown"] = "unknown"
    quality: Quality = "available"
    adjustment: str = "unknown"
    payload_hash: str = ""
    adapter_version: Literal["idq-004@1", "idq-005@1"] = "idq-004@1"
    revision_of: str | None = None
    legacy_aliases: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def honest_availability(self) -> "EvidenceRecord":
        if self.quality == "available" and (
            self.value is None or self.unit == "unknown"
        ):
            raise ValueError("Available evidence requires a value and a known unit")
        if self.point_in_time_status == "verified" and (
            self.published_at is None or self.document_id is None
        ):
            raise ValueError("PIT proof requires publication and document identity")
        if (
            self.period_start
            and self.period_end
            and self.period_start > self.period_end
        ):
            raise ValueError("Reversed period")
        for moment in [self.fetched_at, self.observed_at, self.published_at]:
            if moment is not None and moment.tzinfo is None:
                raise ValueError("Evidence times must be timezone aware")
        return self


EXPECTED_FAMILIES: tuple[Family, ...] = (
    "quote",
    "ohlcv",
    "overview",
    "cash_flow",
    "balance_sheet",
    "news",
    "filing",
)


class EvidenceSnapshot(EvidenceModel):
    schema_version: Literal[1] = 1
    freshness_policy: Literal["diagnostic-close@1", "strategy-contract@1"] = (
        "diagnostic-close@1"
    )
    reconciliation_policy: Literal["like-slot-1e-6@1"] = "like-slot-1e-6@1"
    source_selection: Literal["retain-all-comparable-no-average@1"] = (
        "retain-all-comparable-no-average@1"
    )
    snapshot_id: str
    request_hash: str
    run_id: str
    symbol: str
    requested_as_of: datetime
    mode: Literal["research", "strict_historical"] = "research"
    state: Literal["collecting", "sealed", "failed", "cancelled"] = "collecting"
    generation: int = 1
    owner: str
    lease_until: datetime
    created_at: datetime
    sealed_at: datetime | None = None
    parent_id: str | None = None
    risk_snapshot_id: str | None = None
    policy_revision: int | None = None
    strategy_version: str | None = None
    strategy_contract: StrategyVersion | None = None
    strategy_peers: dict[str, str] = Field(default_factory=dict)
    records: list[EvidenceRecord] = Field(default_factory=list, max_length=1000)
    expected: list[Family] = Field(default_factory=lambda: list(EXPECTED_FAMILIES))
    coverage: dict[str, Quality] = Field(default_factory=dict)
    conflicts: dict[str, list[str]] = Field(default_factory=dict)
    manifest_hash: str = ""
    error_code: str | None = None


class ResearchClaim(EvidenceModel):
    kind: Literal["fact", "derived", "hypothesis", "judgment"]
    symbol: str
    metric: str
    value: Number | str | None = None
    unit: str = "unknown"
    period: Period = "unknown"
    period_end: date | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    method: Literal["free_cash_flow@1", "net_margin@1"] | None = None
    text: str = Field(default="", max_length=1000)


class ClaimResult(EvidenceModel):
    claim_id: str
    claim: ResearchClaim
    status: Literal["matches_snapshot", "unverified", "rejected"]
    reasons: list[str]
    evidence_ids: list[str]
    computed_value: Number | None = None


class ResearchDossier(EvidenceModel):
    schema_version: Literal[1] = 1
    dossier_id: str
    snapshot_id: str
    manifest_hash: str
    run_id: str
    symbol: str
    report_hash: str
    claims: list[ClaimResult] = Field(max_length=64)
    errors: list[str]
    prose_verification: Literal["unverified"] = "unverified"
    actionable: Literal[False] = False


class EvidenceSummary(EvidenceModel):
    snapshot_ids: list[str]
    dossier_ids: list[str]
    errors: list[str]
    prose_verification: Literal["unverified"] = "unverified"
    actionable: Literal[False] = False
