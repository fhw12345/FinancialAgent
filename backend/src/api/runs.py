"""Read-only APIs for shared durable agent runs."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..database.repositories.agent_run_repository import AgentRunRepository
from ..models.agent_run import AgentRun
from .dependencies.run_deps import get_agent_run_repository

router = APIRouter(prefix="/api/runs", tags=["agent-runs"])


@router.get("/{run_id}", response_model=AgentRun)
async def get_run(
    run_id: str,
    repository: AgentRunRepository = Depends(get_agent_run_repository),
) -> AgentRun:
    run = await repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("", response_model=list[AgentRun])
async def list_runs(
    chat_id: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    repository: AgentRunRepository = Depends(get_agent_run_repository),
) -> list[AgentRun]:
    return await repository.list_by_chat(chat_id, limit=limit)
