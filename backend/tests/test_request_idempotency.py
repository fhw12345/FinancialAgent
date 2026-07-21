"""Request-ID claim and replay coverage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api.chat.streaming.handlers import (
    _replay_existing_run,
    chat_stream_unified,
)
from src.api.schemas.chat_models import ChatRequest
from src.core.utils.date_utils import utcnow
from src.models.agent_run import AgentRun
from src.models.message import Message, MessageMetadata


def completed_run() -> AgentRun:
    return AgentRun(
        run_id="run_existing",
        request_id="request_123",
        chat_id="chat_existing",
        execution_mode="instant",
        requested_policy="auto",
        selected_policy="v2",
        policy_version="auto-router-v1",
        status="completed",
        started_at=utcnow(),
        finished_at=utcnow(),
    )


@pytest.mark.asyncio
async def test_duplicate_request_replays_without_routing_or_agent_execution():
    run_service = AsyncMock()
    run_service.claim_chat_run.return_value = (completed_run(), False)
    message_repo = AsyncMock()
    message_repo.get_by_run_id.return_value = Message(
        message_id="msg_run",
        chat_id="chat_existing",
        role="assistant",
        content="Persisted answer",
        source="llm",
        timestamp=utcnow(),
        metadata=MessageMetadata(
            run_id="run_existing",
            run_status="completed",
        ),
    )
    flow_router = AsyncMock()
    simple_agent = Mock()

    response = await chat_stream_unified(
        request=ChatRequest(
            message="Explain P/E",
            request_id="request_123",
            agent_version="auto",
        ),
        http_request=SimpleNamespace(is_disconnected=AsyncMock(return_value=False)),
        chat_service=AsyncMock(),
        simple_agent=simple_agent,
        react_agent=Mock(),
        deep_agent=Mock(),
        context_manager=Mock(),
        message_repo=message_repo,
        flow_router=flow_router,
        run_service=run_service,
        x_debug=None,
    )

    output = ""
    async for chunk in response.body_iterator:
        output += chunk.decode() if isinstance(chunk, bytes) else chunk

    assert "Persisted answer" in output
    assert '"request_reused": true' in output
    flow_router.select.assert_not_awaited()
    assert not simple_agent.method_calls


@pytest.mark.asyncio
async def test_claim_chat_run_returns_repository_winner():
    repository = AsyncMock()
    repository.claim_request_run.return_value = (completed_run(), False)
    from src.services.agent_run_service import AgentRunService

    run, owns_execution = await AgentRunService(repository).claim_chat_run(
        requested_policy="auto",
        request_id="request_123",
    )

    candidate = repository.claim_request_run.await_args.args[0]
    assert candidate.request_id == "request_123"
    assert run.run_id == "run_existing"
    assert owns_execution is False


@pytest.mark.asyncio
async def test_cancelled_replay_without_message_has_visible_content():
    run = completed_run().model_copy(
        update={
            "status": "cancelled",
            "finished_at": utcnow(),
        }
    )
    response = _replay_existing_run(run, None)

    output = ""
    async for chunk in response.body_iterator:
        output += chunk

    assert "Request cancelled." in output
    assert '"type": "cancelled"' in output
