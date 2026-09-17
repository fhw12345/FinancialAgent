"""Read-only sealed evidence navigation; no arbitrary URL proxy, file access or approval."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database.mongodb import MongoDB
from ...database.repositories.evidence_repository import EvidenceRepository
from ..copilot import no_store
from ..dependencies.storage import get_mongodb

router = APIRouter(prefix="/evidence", dependencies=[Depends(no_store)])


@router.get("/snapshots/{snapshot_id}")
async def snapshot_detail(
    snapshot_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: MongoDB = Depends(get_mongodb),
) -> dict[str, Any]:
    snapshot = await EvidenceRepository(db).get(snapshot_id)
    output = snapshot.model_dump(
        mode="json", exclude={"records", "owner", "lease_until"}
    )
    output.update(
        records=[
            r.model_dump(mode="json") for r in snapshot.records[offset : offset + limit]
        ],
        records_count=len(snapshot.records),
        offset=offset,
        limit=limit,
    )
    return output


@router.get("/records/{evidence_id}")
async def record_detail(
    evidence_id: str,
    snapshot_id: str = Query(..., max_length=100),
    db: MongoDB = Depends(get_mongodb),
) -> dict[str, Any]:
    snapshot = await EvidenceRepository(db).get(snapshot_id)
    for record in snapshot.records:
        if record.evidence_id == evidence_id:
            return record.model_dump(mode="json")
    raise HTTPException(404, "Evidence is not a member of this sealed manifest")


@router.get("/runs/{run_id}")
async def run_evidence(
    run_id: str, db: MongoDB = Depends(get_mongodb)
) -> dict[str, Any] | None:
    from ...models.evidence import EvidenceSummary

    repository = EvidenceRepository(db)
    cursor = db.get_collection("research_dossiers").find({"run_id": run_id}).limit(100)
    dossiers = [await repository.get_dossier(row["dossier_id"]) async for row in cursor]
    if not dossiers:
        return None
    return EvidenceSummary(
        snapshot_ids=sorted({d.snapshot_id for d in dossiers}),
        dossier_ids=[d.dossier_id for d in dossiers],
        errors=sorted({e for d in dossiers for e in d.errors}),
    ).model_dump(mode="json")


@router.get("/dossiers/{dossier_id}")
async def dossier_detail(
    dossier_id: str, db: MongoDB = Depends(get_mongodb)
) -> dict[str, Any]:
    dossier = await EvidenceRepository(db).get_dossier(dossier_id)
    run = await db.get_collection("agent_runs").find_one({"run_id": dossier.run_id})
    return {
        "dossier": dossier.model_dump(mode="json"),
        "run_status": run.get("status") if run else None,
    }
