"""Responses message conversion and LF-framed SSE parsing (no tool execution)."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from .protocol import CopilotError


def text_content(message: BaseMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    parts = []
    for block in message.content:
        if isinstance(block, str):
            parts.append(block)
        elif (
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ):
            parts.append(block["text"])
        else:
            raise CopilotError("unsupported_non_text_input", 422)
    return "\n".join(parts)


def response_input(
    messages: list[BaseMessage], model: str
) -> tuple[str, list[dict[str, Any]]]:
    instructions: list[str] = []
    items: list[dict[str, Any]] = []
    for message in messages:
        text = text_content(message)
        if isinstance(message, SystemMessage):
            instructions.append(text)
        elif isinstance(message, ToolMessage):
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": text,
                }
            )
        elif isinstance(message, HumanMessage):
            items.append(
                {"role": "user", "content": [{"type": "input_text", "text": text}]}
            )
        elif isinstance(message, AIMessage):
            raw = message.additional_kwargs.get("copilot_output")
            if raw and message.response_metadata.get("model_name") == model:
                # Opaque reasoning IDs/encrypted content must survive within a
                # tool loop; never send signed items to a different model.
                items.extend(raw)
            else:
                if text:
                    items.append(
                        {
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": text}],
                        }
                    )
                for call in message.tool_calls:
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": call["id"],
                            "name": call["name"],
                            "arguments": json.dumps(call["args"], ensure_ascii=False),
                        }
                    )
        else:
            raise CopilotError("unsupported_message_type", 422)
    return "\n\n".join(instructions), items


async def sse_events(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Split only on LF: Unicode line separators inside JSON are valid text."""
    buffer = ""
    data: list[str] = []
    event_size = 0
    async for part in response.aiter_text():
        buffer += part
        if len(buffer) > 2_000_000:
            raise CopilotError("stream_event_too_large")
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.removesuffix("\r")
            if line.startswith("data:"):
                value = line[5:].lstrip(" ")
                data.append(value)
                event_size += len(value)
                if event_size > 2_000_000:
                    raise CopilotError("stream_event_too_large")
            elif line == "" and data:
                payload = "\n".join(data)
                data, event_size = [], 0
                if payload == "[DONE]":
                    continue
                try:
                    event = json.loads(payload)
                except ValueError:
                    raise CopilotError("invalid_stream_event") from None
                if not isinstance(event, dict):
                    raise CopilotError("invalid_stream_event")
                yield event
    if buffer.strip() or data:
        raise CopilotError("truncated_stream_event")


class ResponseChunks:
    """Translate deltas exactly once and require a successful terminal event."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.completed = False
        self.tools: set[int] = set()
        self.argument_deltas: set[int] = set()
        self.text_seen = False
        self.arguments: dict[int, str] = {}
        self.identities: dict[int, tuple[str, str]] = {}

    def feed(self, event: dict[str, Any]) -> list[AIMessageChunk]:
        if self.completed:
            raise CopilotError("events_after_completion")
        kind = event.get("type")
        chunks = []
        if kind in ("error", "response.failed", "response.incomplete"):
            raise CopilotError(
                "response_incomplete"
                if kind == "response.incomplete"
                else "inference_failed"
            )
        if kind == "response.output_text.delta":
            delta = event.get("delta")
            if not isinstance(delta, str):
                raise CopilotError("invalid_text_delta")
            self.text_seen = True
            chunks.append(AIMessageChunk(content=delta))
        elif kind in ("response.output_item.added", "response.output_item.done"):
            item = event.get("item", {})
            index = event.get("output_index", 0)
            if not isinstance(item, dict) or not isinstance(index, int):
                raise CopilotError("invalid_output_item")
            if item.get("type") == "function_call":
                if index not in self.tools:
                    if not isinstance(item.get("call_id"), str) or not isinstance(
                        item.get("name"), str
                    ):
                        raise CopilotError("invalid_tool_call")
                    chunks.append(
                        AIMessageChunk(
                            content="",
                            tool_call_chunks=[
                                {
                                    "name": item["name"],
                                    "id": item["call_id"],
                                    "args": "",
                                    "index": index,
                                }
                            ],
                        )
                    )
                    self.tools.add(index)
                    self.identities[index] = (item["call_id"], item["name"])
                elif self.identities[index] != (item.get("call_id"), item.get("name")):
                    raise CopilotError("tool_identity_changed")
                if kind.endswith("done"):
                    self._validate_arguments(item.get("arguments"), index)
                if kind.endswith("done") and index not in self.argument_deltas:
                    args = item.get("arguments", "")
                    if not isinstance(args, str):
                        raise CopilotError("invalid_tool_arguments")
                    chunks.append(
                        AIMessageChunk(
                            content="",
                            tool_call_chunks=[
                                {"name": None, "id": None, "args": args, "index": index}
                            ],
                        )
                    )
                    self.argument_deltas.add(index)
                    self.arguments[index] = args
        elif kind == "response.function_call_arguments.delta":
            index, delta = event.get("output_index"), event.get("delta")
            if (
                not isinstance(index, int)
                or index not in self.tools
                or not isinstance(delta, str)
            ):
                raise CopilotError("invalid_tool_delta")
            self.argument_deltas.add(index)
            self.arguments[index] = self.arguments.get(index, "") + delta
            chunks.append(
                AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {"name": None, "id": None, "args": delta, "index": index}
                    ],
                )
            )
        elif kind == "response.completed":
            body = event.get("response", {})
            if not isinstance(body, dict) or body.get("status") != "completed":
                raise CopilotError("inference_failed")
            output = body.get("output")
            usage = body.get("usage")
            if not isinstance(output, list) or not isinstance(usage, dict):
                raise CopilotError("missing_terminal_output_or_usage")
            if not all(isinstance(item, dict) for item in output):
                raise CopilotError("invalid_output_item")
            for index, item in enumerate(output):
                if item.get("type") == "function_call":
                    self._validate_arguments(item.get("arguments"), index)
                    if index in self.identities and self.identities[index] != (
                        item.get("call_id"),
                        item.get("name"),
                    ):
                        raise CopilotError("tool_identity_changed")
            if not self.text_seen:
                for item in output:
                    if item.get("type") == "message":
                        for block in item.get("content", []):
                            if not isinstance(block, dict):
                                raise CopilotError("invalid_output_item")
                            if block.get("type") == "output_text":
                                chunks.append(AIMessageChunk(content=block["text"]))
                                self.text_seen = True
            # Some endpoints emit function calls only in the terminal output.
            for index, item in enumerate(output):
                if item.get("type") == "function_call" and index not in self.tools:
                    chunks.extend(
                        self.feed(
                            {
                                "type": "response.output_item.done",
                                "item": item,
                                "output_index": index,
                            }
                        )
                    )
            if not self.text_seen and not self.tools:
                raise CopilotError("empty_model_response")
            input_tokens, output_tokens = usage.get("input_tokens"), usage.get(
                "output_tokens"
            )
            if (
                not isinstance(input_tokens, int)
                or not isinstance(output_tokens, int)
                or min(input_tokens, output_tokens) < 0
            ):
                raise CopilotError("invalid_usage")
            cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
            if not isinstance(cached, int) or not 0 <= cached <= input_tokens:
                raise CopilotError("invalid_usage")
            chunks.append(
                AIMessageChunk(
                    content="",
                    additional_kwargs={"copilot_output": output},
                    response_metadata={
                        "model_name": self.model,
                        "finish_reason": "tool_calls" if self.tools else "stop",
                    },
                    usage_metadata={
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                        "input_token_details": {"cache_read": cached},
                    },
                )
            )
            self.completed = True
        return chunks

    def _validate_arguments(self, raw: Any, index: int) -> None:
        if not isinstance(raw, str):
            raise CopilotError("invalid_tool_arguments")
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("Tool arguments must be an object")
            # Deltas and final output must describe the same call, not two
            # different instructions for the executor and subsequent replay.
            if index in self.arguments and json.loads(self.arguments[index]) != parsed:
                raise ValueError("Mismatched tool arguments")
        except ValueError:
            raise CopilotError("invalid_tool_arguments") from None
