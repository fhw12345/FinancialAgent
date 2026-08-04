from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import AsyncCallbackHandler
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool

from src.core.utils import message_content_to_text

from .live_schemas import ToolEvidence

_SOURCE_ID_RE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9:._-]{3,})\]")
_FAILURE_OUTPUT_RE = re.compile(
    r"^\s*(?:error\b|failed to\b|no .+ data available\b|" r".+\bunavailable for\b)",
    re.IGNORECASE,
)


def _source_identity(output: str) -> tuple[str | None, str | None]:
    match = _SOURCE_ID_RE.search(output)
    if match is None:
        return None, None
    source_id = match.group(1)
    provider = (
        "replay"
        if source_id.startswith("REPLAY-")
        else source_id.split(":", 1)[0].lower()
    )
    return source_id, provider


def _output_succeeded(output: str) -> bool:
    return not _FAILURE_OUTPUT_RE.search(output)


class EvaluationToolTraceCallback(AsyncCallbackHandler):
    """Capture per-tool latency without coupling evaluation to SSE callbacks."""

    def __init__(self) -> None:
        super().__init__()
        self._active: dict[UUID, tuple[str, float]] = {}
        self.completed: list[tuple[str, float, bool]] = []

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del input_str, kwargs
        self._active[run_id] = (
            str(serialized.get("name", "unknown_tool")),
            time.perf_counter(),
        )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del kwargs
        name, started = self._active.pop(
            run_id,
            ("unknown_tool", time.perf_counter()),
        )
        self.completed.append(
            (
                name,
                (time.perf_counter() - started) * 1000,
                _output_succeeded(str(output)),
            )
        )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del error, kwargs
        name, started = self._active.pop(
            run_id,
            ("unknown_tool", time.perf_counter()),
        )
        self.completed.append((name, (time.perf_counter() - started) * 1000, False))


def collect_tool_evidence(
    messages: Sequence[Any],
    timings: Sequence[tuple[str, float, bool]] = (),
) -> list[ToolEvidence]:
    call_arguments: dict[str, dict[str, object]] = {}
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            call_id = str(call.get("id", ""))
            args = call.get("args")
            call_arguments[call_id] = args if isinstance(args, dict) else {}

    timing_by_name: dict[str, deque[tuple[float, bool]]] = defaultdict(deque)
    for name, duration_ms, success in timings:
        timing_by_name[name].append((duration_ms, success))

    evidence: list[ToolEvidence] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        output = message_content_to_text(message.content)
        source_id, provider = _source_identity(output)
        tool_name = message.name or "unknown_tool"
        duration_ms, callback_success = (
            timing_by_name[tool_name].popleft()
            if timing_by_name[tool_name]
            else (0.0, True)
        )
        evidence.append(
            ToolEvidence(
                tool_name=tool_name,
                arguments=call_arguments.get(message.tool_call_id, {}),
                output=output,
                source_id=source_id,
                provider=provider,
                duration_ms=duration_ms,
                success=(
                    callback_success
                    and message.status != "error"
                    and _output_succeeded(output)
                ),
            )
        )
    return evidence


async def invoke_tool_with_evidence(
    tool: BaseTool,
    arguments: dict[str, object],
) -> ToolEvidence:
    started = time.perf_counter()
    try:
        output = str(await tool.ainvoke(arguments))
    except Exception as exc:
        return ToolEvidence(
            tool_name=tool.name,
            arguments=arguments,
            output=f"{type(exc).__name__}: {exc}",
            duration_ms=(time.perf_counter() - started) * 1000,
            success=False,
        )
    source_id, provider = _source_identity(output)
    return ToolEvidence(
        tool_name=tool.name,
        arguments=arguments,
        output=output,
        source_id=source_id,
        provider=provider,
        duration_ms=(time.perf_counter() - started) * 1000,
        success=_output_succeeded(output),
    )
