"""Unit tests for the shared Direct/ReAct/Deep chat lifecycle."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api.chat.streaming.lifecycle import (
    ChatClarification,
    ChatCompletion,
    ChatFailure,
    ChatStreamLifecycle,
)
from src.api.schemas.chat_models import ChatRequest
from src.core.utils.date_utils import utcnow
from src.models.agent_run import AgentRun
from src.models.message import Message, MessageMetadata


def make_context_manager() -> Mock:
    manager = Mock()
    manager.calculate_context_tokens.return_value = 0
    manager.estimate_tokens.return_value = 1
    manager.should_compact.return_value = False
    return manager


def make_chat_service() -> AsyncMock:
    service = AsyncMock()
    service.get_chat.return_value = SimpleNamespace(
        chat_id="chat_lifecycle",
        ui_state=None,
    )
    service.add_message.return_value = Message(
        message_id="msg_current",
        chat_id="chat_lifecycle",
        role="user",
        content="Analyze AAPL",
        source="user",
        timestamp=utcnow(),
    )
    service.get_chat_messages.return_value = []
    return service


def make_run(status: str) -> AgentRun:
    return AgentRun(
        run_id="run_lifecycle",
        requested_policy="auto",
        selected_policy="v3",
        policy_version="auto-router-v1",
        execution_mode="agentic",
        status=status,  # type: ignore[arg-type]
        started_at=utcnow(),
    )


def parse_events(events: list[str]) -> list[dict]:
    return [json.loads(event.removeprefix("data: ").strip()) for event in events]


async def collect_events(events) -> list[str]:
    return [event async for event in events]


def make_lifecycle(
    *,
    request: ChatRequest | None = None,
) -> tuple[ChatStreamLifecycle, AsyncMock, AsyncMock]:
    chat_service = make_chat_service()
    run_service = AsyncMock()
    lifecycle = ChatStreamLifecycle(
        request=request
        or ChatRequest(
            message="Analyze AAPL",
            chat_id="chat_lifecycle",
            agent_version="v3",
            language="en",
            current_symbol="AAPL",
        ),
        user_id="local",
        chat_service=chat_service,
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
        route_metadata={
            "flow": "v3",
            "source": "rule",
            "reason_code": "explicit_symbol_analysis",
        },
        run_id="run_lifecycle",
        run_service=run_service,
    )
    return lifecycle, chat_service, run_service


@pytest.mark.asyncio
async def test_start_and_prepare_share_chat_run_message_and_context_setup():
    lifecycle, chat_service, run_service = make_lifecycle()

    created_event = await lifecycle.start()
    prepared = await lifecycle.prepare_context(include_symbol_context=True)

    assert created_event is None
    assert prepared is not None
    assert prepared.current_message.startswith("Analyze AAPL")
    assert "selected symbol 'AAPL'" in prepared.current_message
    run_service.attach_chat.assert_awaited_once_with(
        "run_lifecycle",
        "chat_lifecycle",
    )
    chat_service.add_message.assert_awaited_once()
    chat_service.update_title_if_new.assert_awaited_once_with(
        chat_id="chat_lifecycle",
        llm_title=None,
        user_message="Analyze AAPL",
        current_symbol="AAPL",
    )


@pytest.mark.asyncio
async def test_non_user_message_is_persisted_without_context_or_title_work():
    lifecycle, chat_service, _ = make_lifecycle(
        request=ChatRequest(
            message="Tool output",
            chat_id="chat_lifecycle",
            role="assistant",
            source="tool",
            agent_version="v2",
        )
    )

    await lifecycle.start()
    prepared = await lifecycle.prepare_context(include_symbol_context=True)

    assert prepared is None
    chat_service.add_message.assert_awaited_once()
    chat_service.get_chat_messages.assert_not_awaited()
    chat_service.update_title_if_new.assert_not_awaited()


@pytest.mark.asyncio
async def test_completion_persists_message_run_title_and_terminal_events():
    lifecycle, chat_service, run_service = make_lifecycle()
    run_service.complete.return_value = make_run("completed")
    await lifecycle.start()

    events = await collect_events(
        lifecycle.complete(
            ChatCompletion(
                content="Completed answer",
                execution_mode="agentic",
                agent_type="react_sdk",
                llm_title="AAPL outlook",
                update_final_title=True,
                trace_id="trace_1",
                tool_calls=2,
                input_tokens=10,
                output_tokens=5,
                raw_data={"agent_type": "react_sdk"},
                latency_metrics={"tool_executions": 2},
                done_data={"tool_executions": 2, "trace_id": "trace_1"},
            )
        )
    )

    metadata = chat_service.upsert_run_message.await_args.kwargs["metadata"]
    assert isinstance(metadata, MessageMetadata)
    assert metadata.run_status == "completed"
    assert metadata.trace_id == "trace_1"
    run_service.complete.assert_awaited_once_with(
        "run_lifecycle",
        tool_calls=2,
        input_tokens=10,
        output_tokens=5,
    )
    chat_service.update_title_if_new.assert_awaited_once_with(
        chat_id="chat_lifecycle",
        llm_title="AAPL outlook",
        user_message="Analyze AAPL",
        current_symbol=None,
    )
    parsed = parse_events(events)
    assert [event["type"] for event in parsed] == [
        "run_state",
        "latency",
        "done",
    ]
    assert parsed[-1]["trace_id"] == "trace_1"


@pytest.mark.asyncio
async def test_completion_transition_failure_compensates_terminal_message():
    lifecycle, chat_service, run_service = make_lifecycle()
    run_service.complete.side_effect = RuntimeError("run store unavailable")
    run_service.fail.return_value = make_run("failed")
    await lifecycle.start()

    events = await collect_events(
        lifecycle.complete(
            ChatCompletion(
                content="Generated answer",
                execution_mode="agentic",
                agent_type="react_sdk",
                trace_id="trace_failure",
                raw_data={"agent_type": "react_sdk"},
            )
        )
    )

    statuses = [
        call.kwargs["metadata"].run_status
        for call in chat_service.upsert_run_message.await_args_list
    ]
    assert statuses == ["completed", "failed"]
    compensated = chat_service.upsert_run_message.await_args.kwargs["metadata"]
    assert compensated.raw_data is not None
    assert (
        compensated.raw_data["completion_persistence_error"] == "run store unavailable"
    )
    run_service.fail.assert_awaited_once_with(
        "run_lifecycle",
        error_code="RUN_COMPLETION_PERSISTENCE_ERROR",
        error_message="run store unavailable",
    )
    assert [event["type"] for event in parse_events(events)] == [
        "error",
        "run_state",
    ]


@pytest.mark.asyncio
async def test_completed_run_state_is_emitted_before_final_title_io():
    lifecycle, chat_service, run_service = make_lifecycle()
    run_service.complete.return_value = make_run("completed")
    await lifecycle.start()

    completion_stream = lifecycle.complete(
        ChatCompletion(
            content="Completed answer",
            execution_mode="agentic",
            agent_type="react_sdk",
            llm_title="Deferred title",
            update_final_title=True,
        )
    )
    first_event = json.loads(
        (await anext(completion_stream)).removeprefix("data: ").strip()
    )

    assert first_event["type"] == "run_state"
    assert first_event["status"] == "completed"
    chat_service.update_title_if_new.assert_not_awaited()
    await completion_stream.aclose()


@pytest.mark.asyncio
async def test_failure_and_clarification_keep_legacy_event_shapes():
    lifecycle, chat_service, run_service = make_lifecycle()
    run_service.fail.return_value = make_run("failed")
    run_service.wait_for_input.return_value = make_run("waiting_for_input")
    await lifecycle.start()

    failure_events = await collect_events(
        lifecycle.fail(
            ChatFailure(
                execution_mode="agentic",
                error_code="AGENT_ERROR",
                error_message="provider unavailable",
                client_message="Agent execution failed: provider unavailable",
            )
        )
    )
    catch_all_events = await collect_events(
        lifecycle.fail(
            ChatFailure(
                execution_mode="agentic",
                error_code="STREAM_ERROR",
                error_message="unexpected failure",
                client_message="unexpected failure",
                include_error_code=False,
            )
        )
    )
    clarification_events = await collect_events(
        lifecycle.clarify(
            ChatClarification(
                execution_mode="research",
                agent_type="deep_react",
                content="Please select a company.",
                payload={
                    "clarification_type": "symbol",
                    "reason_code": "ambiguous_symbol",
                    "message": "Please select a company.",
                    "candidates": [],
                },
            )
        )
    )

    assert [event["type"] for event in parse_events(failure_events)] == [
        "error",
        "run_state",
    ]
    assert [event["type"] for event in parse_events(catch_all_events)] == [
        "error",
        "run_state",
    ]
    assert [event["type"] for event in parse_events(clarification_events)] == [
        "clarification_required",
        "run_state",
        "done",
    ]
    assistant_call = chat_service.add_message.await_args
    assert assistant_call.kwargs["metadata"]["run_status"] == "waiting_for_input"


@pytest.mark.asyncio
async def test_error_and_clarification_emit_before_transition_failure():
    lifecycle, _, run_service = make_lifecycle()
    await lifecycle.start()
    run_service.fail.side_effect = RuntimeError("run store unavailable")
    run_service.wait_for_input.side_effect = RuntimeError("run store unavailable")

    failure_stream = lifecycle.fail(
        ChatFailure(
            execution_mode="agentic",
            error_code="AGENT_ERROR",
            error_message="provider unavailable",
            client_message="Agent execution failed",
        )
    )
    assert [
        event["type"] for event in parse_events(await collect_events(failure_stream))
    ] == ["error"]

    catch_all_stream = lifecycle.fail(
        ChatFailure(
            execution_mode="agentic",
            error_code="STREAM_ERROR",
            error_message="unexpected failure",
            client_message="unexpected failure",
            include_error_code=False,
        )
    )
    assert [
        event["type"] for event in parse_events(await collect_events(catch_all_stream))
    ] == ["error"]

    run_service.fail.side_effect = None
    run_service.fail.return_value = make_run("failed")
    clarification_stream = lifecycle.clarify(
        ChatClarification(
            execution_mode="research",
            agent_type="deep_react",
            content="Please select a company.",
            payload={
                "clarification_type": "symbol",
                "reason_code": "ambiguous_symbol",
                "message": "Please select a company.",
                "candidates": [],
            },
        )
    )
    assert [
        event["type"]
        for event in parse_events(await collect_events(clarification_stream))
    ] == ["clarification_required", "error", "run_state"]
    compensated = lifecycle.chat_service.upsert_run_message.await_args.kwargs[
        "metadata"
    ]
    assert compensated.run_status == "failed"
    assert compensated.raw_data is not None
    assert "clarification_required" not in compensated.raw_data
    assert (
        compensated.raw_data["failed_clarification"]["reason_code"]
        == "ambiguous_symbol"
    )
    assert (
        compensated.raw_data["clarification_persistence_error"]
        == "waiting-for-input transition failed"
    )
    assert run_service.fail.await_count == 3
    run_service.wait_for_input.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_without_started_chat_still_transitions_run():
    lifecycle, chat_service, run_service = make_lifecycle()
    run_service.cancel.return_value = make_run("cancelled")

    await lifecycle.cancel(
        active_task=None,
        agent_type="react_sdk",
        cancel_reason="client_disconnected_before_setup",
    )

    run_service.cancel.assert_awaited_once_with(
        "run_lifecycle",
        cancel_reason="client_disconnected_before_setup",
    )
    chat_service.upsert_run_message.assert_not_awaited()
