"""Copilot Chat Completions conversion/streaming for Gemini, without a bridge."""

import copy
import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from .protocol import CopilotError
from .responses import text_content


def chat_input(
    messages: list[BaseMessage], model: str, role: str
) -> list[dict[str, Any]]:
    result = []
    for message in messages:
        text = text_content(message)
        if isinstance(message, (SystemMessage, HumanMessage)):
            result.append(
                {
                    "role": "system" if isinstance(message, SystemMessage) else "user",
                    "content": text,
                }
            )
        elif isinstance(message, ToolMessage):
            result.append(
                {"role": "tool", "tool_call_id": message.tool_call_id, "content": text}
            )
        elif isinstance(message, AIMessage):
            raw = message.additional_kwargs.get("copilot_chat_message")
            if (
                raw
                and message.response_metadata.get("model_name") == model
                and message.response_metadata.get("copilot_role") == role
            ):
                result.append(copy.deepcopy(raw))
                continue
            assistant: dict[str, Any] = {"role": "assistant", "content": text or None}
            if message.tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c["args"], ensure_ascii=False),
                        },
                    }
                    for c in message.tool_calls
                ]
            if text or message.tool_calls:
                result.append(assistant)
        else:
            raise CopilotError("unsupported_message_type", 422)
    return result


class ChatChunks:
    """Wait for finish_reason AND usage, then publish exactly one final receipt."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.completed = False
        self.finish_reason: str | None = None
        self.text = ""
        self.calls: dict[int, dict[str, Any]] = {}
        self.replay: dict[str, Any] = {}
        self.usage: dict[str, Any] | None = None
        self.size = 0

    def feed(self, event: dict[str, Any]) -> list[AIMessageChunk]:
        if event.get("error"):
            raise CopilotError("inference_failed")
        self.size += len(json.dumps(event))
        if self.size > 8_000_000:
            raise CopilotError("stream_too_large")
        usage = event.get("usage")
        if isinstance(usage, dict):
            self.usage = usage
        choices = event.get("choices")
        if not isinstance(choices, list) or len(choices) > 1:
            raise CopilotError("invalid_chat_chunk")
        if not choices:
            return []
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get("index", 0) != 0:
            raise CopilotError("invalid_chat_chunk")
        if self.finish_reason is not None:
            raise CopilotError("events_after_completion")
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            raise CopilotError("invalid_chat_delta")
        chunks = []
        text = delta.get("content")
        if text is not None:
            if not isinstance(text, str):
                raise CopilotError("unsupported_non_text_output")
            self.text += text
            if text:
                chunks.append(AIMessageChunk(content=text))
        if delta.get("refusal"):
            raise CopilotError("model_refused")
        for field in ("reasoning_content", "reasoning", "reasoning_text"):
            if field in delta:
                if not isinstance(delta[field], str):
                    raise CopilotError("invalid_reasoning_metadata")
                self.replay[field] = self.replay.get(field, "") + delta[field]
        if "reasoning_details" in delta:
            if not isinstance(delta["reasoning_details"], list):
                raise CopilotError("invalid_reasoning_metadata")
            self.replay.setdefault("reasoning_details", []).extend(
                copy.deepcopy(delta["reasoning_details"])
            )
        for tool in delta.get("tool_calls") or []:
            if not isinstance(tool, dict) or not isinstance(tool.get("index"), int):
                raise CopilotError("invalid_tool_delta")
            index = tool["index"]
            call = self.calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
            function = tool.get("function") or {}
            if (
                not isinstance(function, dict)
                or tool.get("type", "function") != "function"
            ):
                raise CopilotError("unsupported_tool_type")
            name, call_id = function.get("name"), tool.get("id")
            for field, value in (("id", call_id), ("name", name)):
                if value is not None:
                    if not isinstance(value, str) or (
                        call[field] and value != call[field]
                    ):
                        raise CopilotError("tool_identity_changed")
                    if call[field]:
                        if field == "id":
                            call_id = None
                        else:
                            name = None
                    call[field] = value
            args = function.get("arguments", "")
            if not isinstance(args, str):
                raise CopilotError("invalid_tool_arguments")
            call["arguments"] += args
            if "extra_content" in tool:
                call["extra_content"] = copy.deepcopy(tool["extra_content"])
            chunks.append(
                AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {"index": index, "id": call_id, "name": name, "args": args}
                    ],
                )
            )
        reason = choice.get("finish_reason")
        if reason is not None:
            if reason not in ("stop", "tool_calls"):
                raise CopilotError("response_incomplete")
            self.finish_reason = reason
        return chunks

    def finish(self) -> list[AIMessageChunk]:
        if self.completed or self.finish_reason is None or self.usage is None:
            raise CopilotError("stream_ended_without_completion_or_usage")
        if not self.text and not self.calls:
            raise CopilotError("empty_model_response")
        tools = []
        for _, call in sorted(self.calls.items()):
            try:
                if (
                    not call["id"]
                    or not call["name"]
                    or not isinstance(json.loads(call["arguments"]), dict)
                ):
                    raise ValueError("Invalid tool")
            except ValueError:
                raise CopilotError("invalid_tool_arguments") from None
            tool = {
                "type": "function",
                "id": call["id"],
                "function": {"name": call["name"], "arguments": call["arguments"]},
            }
            if "extra_content" in call:
                tool["extra_content"] = call["extra_content"]
            tools.append(tool)
        if self.finish_reason == "tool_calls" and not tools:
            raise CopilotError("invalid_tool_arguments")
        incoming, outgoing = self.usage.get("prompt_tokens"), self.usage.get(
            "completion_tokens"
        )
        if (
            not isinstance(incoming, int)
            or not isinstance(outgoing, int)
            or min(incoming, outgoing) < 0
        ):
            raise CopilotError("invalid_usage")
        details = self.usage.get("prompt_tokens_details") or {}
        cached = details.get("cached_tokens", 0) if isinstance(details, dict) else -1
        if not isinstance(cached, int) or not 0 <= cached <= incoming:
            raise CopilotError("invalid_usage")
        assistant = {"role": "assistant", "content": self.text or None, **self.replay}
        if tools:
            assistant["tool_calls"] = tools
        self.completed = True
        return [
            AIMessageChunk(
                content="",
                additional_kwargs={"copilot_chat_message": assistant},
                response_metadata={
                    "model_name": self.model,
                    "finish_reason": "tool_calls" if tools else "stop",
                },
                usage_metadata={
                    "input_tokens": incoming,
                    "output_tokens": outgoing,
                    "total_tokens": incoming + outgoing,
                    "input_token_details": {"cache_read": cached},
                },
            )
        ]
