"""Safe content identities and comparable-slot reconciliation; no upstream payload dumping."""

import hashlib
import json
import math
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ...models.evidence import EvidenceRecord, EvidenceSnapshot
from ...shared.sanitizers import sanitize_text


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def safe_uri(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname
            not in {
                "www.sec.gov",
                "sec.gov",
                "finance.yahoo.com",
                "www.alphavantage.co",
            }
            or parsed.port not in (None, 443)
        ):
            return None
        if parsed.username or parsed.password:
            return None
        return urlunsplit(("https", parsed.hostname, parsed.path, "", ""))
    except ValueError:
        return None


def identify(record: EvidenceRecord) -> EvidenceRecord:
    data = record.model_dump(mode="json")
    data["source_uri"] = safe_uri(record.source_uri)
    if isinstance(record.value, str):
        data["value"] = sanitize_text(record.value)[:1000]
    data["document_id"] = (
        sanitize_text(record.document_id)[:150] if record.document_id else None
    )
    data["payload_hash"] = ""
    data["evidence_id"] = ""
    hashed = digest(data)
    data["payload_hash"] = hashed
    data["evidence_id"] = "ev_" + hashed
    return EvidenceRecord.model_validate(data)


def slot(record: EvidenceRecord) -> str:
    return digest(
        [
            record.symbol,
            record.metric,
            record.unit,
            record.period,
            str(record.period_start),
            str(record.period_end),
            str(record.observed_at),
            record.session,
            record.adjustment,
        ]
    )


def reconcile(records: list[EvidenceRecord]) -> dict[str, list[str]]:
    groups: dict[str, list[EvidenceRecord]] = {}
    for record in records:
        # Unknown economic periods cannot be collapsed into one comparable fact.
        if (
            record.quality == "available"
            and record.period != "unknown"
            and (record.period_end or record.observed_at)
        ):
            groups.setdefault(slot(record), []).append(record)
    conflicts = {}
    for key, rows in groups.items():
        first = rows[0].value
        if any(not same_value(first, r.value) for r in rows[1:]):
            conflicts[key] = sorted({r.evidence_id for r in rows})
    return conflicts


def same_value(a: object, b: object) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-8)
    return a == b


def manifest_hash(snapshot: EvidenceSnapshot) -> str:
    return digest(
        {
            "request": snapshot.request_hash,
            "freshness": snapshot.freshness_policy,
            "reconciliation": snapshot.reconciliation_policy,
            "source_selection": snapshot.source_selection,
            "parent": snapshot.parent_id,
            "records": [
                (r.evidence_id, r.payload_hash)
                for r in sorted(snapshot.records, key=lambda r: r.evidence_id)
            ],
            "coverage": snapshot.coverage,
            "conflicts": snapshot.conflicts,
        }
    )
