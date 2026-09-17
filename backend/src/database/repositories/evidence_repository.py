"""Single-document snapshot commits: sealed bytes never change, stale collectors are fenced."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...core.exceptions import AppError
from ...models.evidence import EvidenceRecord, EvidenceSnapshot, ResearchDossier
from ...services.evidence.identity import digest, identify, manifest_hash, reconcile


class EvidenceStorage(Protocol):
    def get_collection(self, name: str) -> Any: ...


class EvidenceConflict(AppError):
    status_code = 409
    error_type = "evidence_snapshot_conflict"


class EvidenceRepository:
    def __init__(self, db: EvidenceStorage):
        self.db = db
        self.collection = db.get_collection("research_snapshots")

    async def begin(
        self,
        *,
        request_key: str,
        run_id: str,
        symbol: str,
        as_of: datetime,
        mode: Literal["research", "strict_historical"] = "research",
        parent_id: str | None = None,
        risk_snapshot_id: str | None = None,
        policy_revision: int | None = None,
    ) -> EvidenceSnapshot:
        identity = {
            "run_id": run_id,
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "mode": mode,
            "parent_id": parent_id,
            "risk_snapshot_id": risk_snapshot_id,
            "policy_revision": policy_revision,
        }
        snapshot_id = "snapshot_" + digest([run_id, request_key, symbol])
        now = datetime.now(UTC)
        fresh = EvidenceSnapshot(
            snapshot_id=snapshot_id,
            request_hash=digest(identity),
            run_id=run_id,
            symbol=symbol,
            requested_as_of=as_of,
            mode=mode,
            owner=uuid4().hex,
            lease_until=now + timedelta(seconds=180),
            created_at=now,
            parent_id=parent_id,
            risk_snapshot_id=risk_snapshot_id,
            policy_revision=policy_revision,
        )
        try:
            row = await self.collection.find_one_and_update(
                {"_id": snapshot_id},
                {"$setOnInsert": fresh.model_dump(mode="json")},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            row = await self.collection.find_one({"_id": snapshot_id})
        if row is None:
            raise RuntimeError("Snapshot creation returned no record")
        row.pop("_id", None)
        existing = EvidenceSnapshot.model_validate(row)
        if existing.request_hash != fresh.request_hash:
            raise EvidenceConflict("Request identity changed")
        if existing.state == "sealed":
            return await self.get(snapshot_id)
        if existing.owner == fresh.owner:
            return existing
        if existing.state == "collecting" and existing.lease_until > now:
            raise EvidenceConflict("Snapshot collection already in progress")
        fresh = fresh.model_copy(
            update={
                "generation": existing.generation + 1,
                "created_at": existing.created_at,
            }
        )
        result = await self.collection.find_one_and_update(
            {
                "_id": snapshot_id,
                "generation": existing.generation,
                "state": existing.state,
            },
            {"$set": fresh.model_dump(mode="json")},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise EvidenceConflict("Snapshot collector changed")
        return fresh

    async def get(self, snapshot_id: str) -> EvidenceSnapshot:
        row = await self.collection.find_one({"_id": snapshot_id})
        if not row or row.get("state") != "sealed":
            raise EvidenceConflict("Only sealed evidence can be consumed")
        row.pop("_id", None)
        snapshot = EvidenceSnapshot.model_validate(row)
        if snapshot.manifest_hash != manifest_hash(snapshot):
            raise EvidenceConflict("Manifest integrity mismatch")
        if any(identify(r).evidence_id != r.evidence_id for r in snapshot.records):
            raise EvidenceConflict("Record integrity mismatch")
        return snapshot

    async def finish(
        self, snapshot: EvidenceSnapshot, records: list[EvidenceRecord]
    ) -> EvidenceSnapshot:
        inherited = []
        if snapshot.parent_id:
            parent = await self.get(snapshot.parent_id)
            if parent.run_id != snapshot.run_id or parent.symbol != snapshot.symbol:
                raise EvidenceConflict("Child must belong to the same run/instrument")
            inherited = parent.records
        unique = {r.evidence_id: r for r in inherited}
        for record in records:
            if (
                record.snapshot_id != snapshot.snapshot_id
                or record.symbol != snapshot.symbol
            ):
                raise EvidenceConflict("Collector record scope mismatch")
            normalized = identify(record)
            unique[normalized.evidence_id] = normalized
        sealed = snapshot.model_copy(
            deep=True,
            update={
                "state": "sealed",
                "records": sorted(unique.values(), key=lambda r: r.evidence_id),
                "sealed_at": datetime.now(UTC),
            },
        )
        sealed = EvidenceSnapshot.model_validate(sealed)
        sealed.conflicts = reconcile(sealed.records)
        conflicting = {eid for ids in sealed.conflicts.values() for eid in ids}
        for family in sealed.expected:
            group = [r for r in sealed.records if r.family == family]
            sealed.coverage[family] = (
                "conflicting"
                if any(r.evidence_id in conflicting for r in group)
                else (
                    "available"
                    if any(r.quality == "available" for r in group)
                    else "missing"
                )
            )
        sealed.manifest_hash = manifest_hash(sealed)
        document = sealed.model_dump(mode="json")
        if len(json.dumps(document).encode()) > 2 * 1024 * 1024:
            raise EvidenceConflict("Snapshot exceeds bounded evidence budget")
        result = await self.collection.find_one_and_update(
            {
                "_id": snapshot.snapshot_id,
                "state": "collecting",
                "owner": snapshot.owner,
                "generation": snapshot.generation,
            },
            {"$set": document},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise EvidenceConflict("Stale collector cannot seal")
        return await self.get(snapshot.snapshot_id)

    async def abort(
        self, snapshot: EvidenceSnapshot, code: str, cancelled: bool = False
    ) -> None:
        await self.collection.update_one(
            {
                "_id": snapshot.snapshot_id,
                "state": "collecting",
                "owner": snapshot.owner,
                "generation": snapshot.generation,
            },
            {
                "$set": {
                    "state": "cancelled" if cancelled else "failed",
                    "error_code": code,
                }
            },
        )

    async def save_dossier(self, dossier: ResearchDossier) -> ResearchDossier:
        await self.db.get_collection("research_dossiers").create_index("run_id")
        snapshot = await self.get(dossier.snapshot_id)
        if (
            snapshot.run_id != dossier.run_id
            or snapshot.manifest_hash != dossier.manifest_hash
        ):
            raise EvidenceConflict("Dossier manifest mismatch")
        result = await self.db.get_collection("research_dossiers").find_one_and_update(
            {"_id": dossier.dossier_id},
            {"$setOnInsert": dossier.model_dump(mode="json")},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("Dossier persistence returned no record")
        result.pop("_id", None)
        if result != dossier.model_dump(mode="json"):
            raise EvidenceConflict("Dossier identity conflict")
        return dossier

    async def get_dossier(self, dossier_id: str) -> ResearchDossier:
        row = await self.db.get_collection("research_dossiers").find_one(
            {"_id": dossier_id}
        )
        if row is None:
            raise EvidenceConflict("Dossier not found")
        row.pop("_id", None)
        dossier = ResearchDossier.model_validate(row)
        snapshot = await self.get(dossier.snapshot_id)
        if (
            dossier.manifest_hash != snapshot.manifest_hash
            or dossier.run_id != snapshot.run_id
        ):
            raise EvidenceConflict("Dossier manifest mismatch")
        return dossier
