"""Dependencies for shared durable agent runs."""

from fastapi import Depends

from ...database.mongodb import MongoDB
from ...database.repositories.agent_run_repository import (
    AGENT_RUNS_COLLECTION,
    AgentRunRepository,
)
from ...services.agent_run_service import AgentRunService
from .storage import get_mongodb


def get_agent_run_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> AgentRunRepository:
    return AgentRunRepository(mongodb.get_collection(AGENT_RUNS_COLLECTION))


def get_agent_run_service(
    repository: AgentRunRepository = Depends(get_agent_run_repository),
) -> AgentRunService:
    return AgentRunService(repository)
