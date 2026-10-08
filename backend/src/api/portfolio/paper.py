"""Isolated manual PAPER journal. No broker, scheduler, AI approval or real ledger mutations."""

from fastapi import APIRouter, Depends, Request

from ...database.mongodb import MongoDB
from ...models.paper_ledger import (
    CreatePaper,
    JournalPaper,
    PaperExperiment,
    PaperView,
    RefreshPaper,
)
from ...services.paper_ledger import service, store
from ..copilot import local_action, no_store
from ..dependencies.rate_limit import limiter
from ..dependencies.storage import get_mongodb

router = APIRouter(prefix="/paper", dependencies=[Depends(no_store)])


@router.get("/experiments", response_model=list[service.PaperSummary])
async def recent(db: MongoDB = Depends(get_mongodb)) -> list[service.PaperSummary]:
    return await service.recent(db)


@router.post(
    "/experiments", response_model=PaperView, dependencies=[Depends(local_action)]
)
async def create(body: CreatePaper, db: MongoDB = Depends(get_mongodb)) -> PaperView:
    return await service.create(db, body)


@router.get("/experiments/{experiment_id}", response_model=PaperView)
async def detail(experiment_id: str, db: MongoDB = Depends(get_mongodb)) -> PaperView:
    return await service.get(db, experiment_id)


@router.post(
    "/experiments/{experiment_id}/journal",
    response_model=PaperView,
    dependencies=[Depends(local_action)],
)
async def journal(
    experiment_id: str, body: JournalPaper, db: MongoDB = Depends(get_mongodb)
) -> PaperView:
    return await service.journal(db, experiment_id, body)


@router.post(
    "/experiments/{experiment_id}/valuation",
    response_model=PaperView,
    dependencies=[Depends(local_action)],
)
@limiter.limit("6/minute")
async def refresh(
    request: Request,
    experiment_id: str,
    body: RefreshPaper,
    db: MongoDB = Depends(get_mongodb),
) -> PaperView:
    return await service.refresh(db, experiment_id, body)


@router.get("/experiments/{experiment_id}/manifest", response_model=PaperExperiment)
async def manifest(
    experiment_id: str, db: MongoDB = Depends(get_mongodb)
) -> PaperExperiment:
    return await store.get(db, experiment_id)
