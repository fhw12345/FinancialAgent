"""Regression tests for the v2 streaming path."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api.chat.streaming.simple_agent import stream_with_simple_agent
from src.api.schemas.chat_models import ChatRequest
from src.core.utils.date_utils import utcnow
from src.models.message import Message


class FakeChatAgent:
    async def stream_chat(self, messages, max_tokens=3000, language="zh-CN"):
        yield "OK"

    def get_last_token_usage(self):
        return None


@pytest.mark.asyncio
async def test_async_generator_streams_without_wait_for_type_error():
    chat_service = AsyncMock()
    chat_service.get_chat.return_value = SimpleNamespace(
        chat_id="chat_1",
        ui_state=None,
    )
    current_message = Message(
        message_id="msg_current",
        chat_id="chat_1",
        role="user",
        content="Explain P/E",
        source="user",
        timestamp=utcnow(),
    )
    chat_service.add_message.return_value = current_message
    chat_service.get_chat_messages.return_value = []
    context_manager = Mock()
    context_manager.calculate_context_tokens.return_value = 0
    context_manager.estimate_tokens.return_value = 1

    response = await stream_with_simple_agent(
        request=ChatRequest(
            message="Explain P/E",
            chat_id="chat_1",
            agent_version="v2",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=FakeChatAgent(),  # type: ignore[arg-type]
        context_manager=context_manager,
        message_repo=AsyncMock(),
        route_metadata={
            "type": "route_selected",
            "flow": "v2",
            "source": "rule",
            "reason_code": "concept_explanation",
        },
    )

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

    output = "".join(chunks)
    assert '"type": "chunk"' in output
    assert '"content": "OK"' in output
    assert '"type": "done"' in output
    assert "STREAM_ERROR" not in output
    chat_service.update_title_if_new.assert_awaited_once_with(
        chat_id="chat_1",
        llm_title=None,
        user_message="Explain P/E",
        current_symbol=None,
    )
