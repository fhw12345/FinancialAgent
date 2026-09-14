"""Snapshot dependency shared by visible refresh and startup wiring."""

from fastapi import HTTPException, Request

from ...services.insights.snapshot_service import InsightsSnapshotService


def get_snapshot_service(request: Request) -> InsightsSnapshotService:
    service = getattr(request.app.state, "snapshot_service", None)
    if not isinstance(service, InsightsSnapshotService):
        raise HTTPException(
            status_code=503, detail="Insights snapshot service unavailable"
        )
    return service
