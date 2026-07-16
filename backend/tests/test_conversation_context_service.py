"""Tests for Mongo-authoritative conversation context preparation."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from src.models.message import Message, MessageMetadata
from src.services.conversation_context_service import ConversationContextService


def message(
    message_id: str,
    role: str,
    content: str,
    *,
    is_summary: bool = False,
) -> Message:
    return Message(
        message_id=message_id,
        chat_id="chat_1",
        role=role,
        content=content,
        source="llm" if role == "assistant" else "user",
        timestamp=datetime.now(UTC),
        metadata=MessageMetadata(is_summary=is_summary),
    )


@pytest.mark.asyncio
async def test_current_turn_is_excluded_by_message_id_not_text():
    previous = message("msg_previous", "user", "Repeat this")
    assistant = message("msg_answer", "assistant", "Previous answer")
    current = message("msg_current", "user", "Repeat this")
    manager = Mock()
    manager.calculate_context_tokens.return_value = 12
    manager.should_compact.return_value = False
    manager.estimate_tokens.return_value = 3
    service = ConversationContextService(manager, AsyncMock())

    prepared = await service.prepare(
        chat_id="chat_1",
        messages=[previous, assistant, current],
        current_message=current,
    )

    assert prepared.history == [
        {"role": "user", "content": "Repeat this"},
        {"role": "assistant", "content": "Previous answer"},
    ]
    assert prepared.complete_history() == [
        {"role": "user", "content": "Repeat this"},
        {"role": "assistant", "content": "Previous answer"},
        {"role": "user", "content": "Repeat this"},
    ]


@pytest.mark.asyncio
async def test_symbol_instruction_is_applied_once_to_current_turn():
    current = message("msg_current", "user", "Analyze this stock")
    manager = Mock()
    manager.calculate_context_tokens.return_value = 0
    manager.should_compact.return_value = False
    manager.estimate_tokens.return_value = 5
    service = ConversationContextService(manager, AsyncMock())
    instruction = "\n\n[Context: selected symbol AAPL]"

    prepared = await service.prepare(
        chat_id="chat_1",
        messages=[current],
        current_message=current,
        symbol_instruction=instruction,
        symbol_source="request",
    )

    assert prepared.current_message.count("selected symbol AAPL") == 1
    assert prepared.symbol_source == "request"


@pytest.mark.asyncio
async def test_compaction_persists_summary_before_deleting_body_ids():
    first = message("msg_1", "user", "old question")
    second = message("msg_2", "assistant", "old answer")
    tail = message("msg_3", "assistant", "recent answer")
    current = message("msg_4", "user", "current question")
    summary = message(
        "msg_summary",
        "assistant",
        "## Previous Conversation Summary\n\nsummary",
        is_summary=True,
    )
    manager = Mock()
    manager.calculate_context_tokens.side_effect = [100, 20]
    manager.should_compact.return_value = True
    manager.extract_context_structure.return_value = ([], [first, second], [tail])
    manager.summarize_history = AsyncMock(return_value="summary")
    manager.estimate_tokens.return_value = 5
    repo = AsyncMock()
    repo.create.return_value = summary
    repo.delete_messages_by_ids.return_value = 2
    service = ConversationContextService(manager, repo)

    prepared = await service.prepare(
        chat_id="chat_1",
        messages=[first, second, tail, current],
        current_message=current,
    )

    assert prepared.compaction_applied is True
    assert prepared.summary_used is True
    assert prepared.history == [
        {
            "role": "assistant",
            "content": "## Previous Conversation Summary\n\nsummary",
        },
        {"role": "assistant", "content": "recent answer"},
    ]
    repo.create.assert_awaited_once()
    create_payload = repo.create.await_args.args[0]
    assert create_payload.timestamp == tail.timestamp - timedelta(microseconds=1)
    repo.delete_messages_by_ids.assert_awaited_once_with(
        chat_id="chat_1",
        message_ids=["msg_1", "msg_2"],
    )


@pytest.mark.asyncio
async def test_empty_history_needs_no_compaction():
    current = message("msg_current", "user", "hello")
    manager = Mock()
    manager.calculate_context_tokens.return_value = 0
    manager.estimate_tokens.return_value = 1
    service = ConversationContextService(manager, AsyncMock())

    prepared = await service.prepare(
        chat_id="chat_1",
        messages=[current],
        current_message=current,
    )

    assert prepared.history == []
    assert prepared.compaction_applied is False
    manager.should_compact.assert_not_called()
