"""Lifecycle service for shared durable agent runs."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from ..agent.llm_factory import get_role_models
from ..core.utils.date_utils import utcnow
from ..database.repositories.agent_run_repository import AgentRunRepository
from ..models.agent_run import AgentRun, AgentRunStatus, ExecutionMode

POLICY_VERSION = "auto-router-v1"
PORTFOLIO_RUN_LEASE = timedelta(hours=2)
PROMPT_VERSIONS: dict[str, str] = {
    "financial-system": "financial-system@3",
    "deep_research": "deep-research-v1",
    "portfolio": "portfolio-v1",
}
FLOW_EXECUTION_MODES: dict[str, ExecutionMode] = {
    "v2": "instant",
    "v3": "agentic",
    "v4-deep": "research",
}

FLOW_MODEL_ROLES: dict[str, tuple[str, ...]] = {
    "v2": ("simple_chat",),
    "v3": ("react_agent",),
    "v4-deep": (
        "deep_planner",
        "sub_technical",
        "sub_news",
        "sub_financial",
        "sub_debater",
        "verdict",
    ),
    "portfolio": ("portfolio_research", "portfolio_decisions"),
}


class AgentRunService:
    """Create and transition shared durable execution records."""

    def __init__(self, repository: AgentRunRepository) -> None:
        self.repository = repository

    async def create_chat_run(
        self,
        *,
        requested_policy: str,
        request_id: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            run_id=f"run_{uuid.uuid4().hex}",
            request_id=request_id,
            requested_policy=requested_policy,
            policy_version=POLICY_VERSION,
            prompt_versions={},
            status="pending",
            started_at=utcnow(),
        )
        return await self.repository.create(run)

    async def claim_chat_run(
        self,
        *,
        requested_policy: str,
        request_id: str | None,
    ) -> tuple[AgentRun, bool]:
        run = AgentRun(
            run_id=f"run_{uuid.uuid4().hex}",
            request_id=request_id,
            requested_policy=requested_policy,
            policy_version=POLICY_VERSION,
            prompt_versions={},
            status="pending",
            started_at=utcnow(),
        )
        return await self.repository.claim_request_run(run)

    async def create_portfolio_run(
        self,
        *,
        portfolio_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[AgentRun, bool]:
        models = get_role_models()
        now = utcnow()
        await self.repository.release_stale_portfolio_claim(
            portfolio_key,
            now=now,
        )
        run = AgentRun(
            run_id=f"run_{uuid.uuid4().hex}",
            portfolio_key=portfolio_key,
            active_portfolio_key=portfolio_key,
            execution_mode="portfolio",
            requested_policy=portfolio_key,
            selected_policy="portfolio",
            policy_version=POLICY_VERSION,
            prompt_versions={"portfolio": PROMPT_VERSIONS["portfolio"]},
            model_routes={role: models[role] for role in FLOW_MODEL_ROLES["portfolio"]},
            status="pending",
            started_at=now,
            lease_expires_at=now + PORTFOLIO_RUN_LEASE,
            metadata=metadata or {},
        )
        return await self.repository.claim_portfolio_run(run)

    async def mark_running(
        self,
        run_id: str,
        *,
        selected_policy: str,
        chat_id: str | None = None,
    ) -> AgentRun | None:
        models = get_role_models()
        roles = FLOW_MODEL_ROLES.get(selected_policy, ())
        prompt_key = {
            "v2": "financial-system",
            "v3": "financial-system",
            "v4-deep": "deep_research",
        }.get(selected_policy)
        return await self.repository.transition(
            run_id,
            from_statuses=("pending", "waiting_for_input"),
            to_status="running",
            chat_id=chat_id,
            execution_mode=FLOW_EXECUTION_MODES.get(selected_policy),
            selected_policy=selected_policy,
            prompt_versions=(
                {prompt_key: PROMPT_VERSIONS[prompt_key]} if prompt_key else {}
            ),
            model_routes={role: models[role] for role in roles},
        )

    async def attach_chat(self, run_id: str, chat_id: str) -> AgentRun | None:
        return await self.repository.update_fields(run_id, chat_id=chat_id)

    async def record_prompt_versions(
        self,
        run_id: str,
        prompt_versions: dict[str, str],
    ) -> AgentRun | None:
        return await self.repository.merge_prompt_versions(
            run_id,
            prompt_versions,
        )

    async def complete(
        self,
        run_id: str,
        *,
        tool_calls: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        data_sources: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun | None:
        return await self.repository.transition(
            run_id,
            from_statuses=("running", "waiting_for_input"),
            to_status="completed",
            finished_at=utcnow(),
            tool_calls=tool_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            data_sources=data_sources or [],
            metadata=metadata or {},
        )

    async def wait_for_input(
        self,
        run_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun | None:
        return await self.repository.transition(
            run_id,
            from_statuses=("pending", "running"),
            to_status="waiting_for_input",
            metadata=metadata or {},
        )

    async def fail(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentRun | None:
        return await self.repository.transition(
            run_id,
            from_statuses=("pending", "running", "waiting_for_input"),
            to_status="failed",
            finished_at=utcnow(),
            error_code=error_code,
            error_message=error_message[:1000],
            metadata=metadata or {},
        )

    async def cancel(
        self,
        run_id: str,
        *,
        cancel_reason: str,
    ) -> AgentRun | None:
        return await self.repository.transition(
            run_id,
            from_statuses=("pending", "running", "waiting_for_input"),
            to_status="cancelled",
            finished_at=utcnow(),
            cancel_reason=cancel_reason,
        )

    async def transition_portfolio(
        self,
        run_id: str,
        *,
        status: AgentRunStatus,
        metadata: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AgentRun | None:
        if status == "running":
            return await self.repository.transition(
                run_id,
                from_statuses=("pending",),
                to_status="running",
            )
        if status == "completed":
            return await self.complete(run_id, metadata=metadata)
        if status == "failed":
            return await self.fail(
                run_id,
                error_code=error_code or "PORTFOLIO_ERROR",
                error_message=error_message or "Portfolio analysis failed",
                metadata=metadata,
            )
        return None
