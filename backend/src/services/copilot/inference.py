"""Model-specific wire payloads; role routing never changes tool permissions."""

from typing import Any

from langchain_core.messages import BaseMessage

from .catalog import CopilotModel
from .completions import ChatChunks, chat_input
from .context import CopilotProfile
from .protocol import CopilotError
from .responses import ResponseChunks, response_input


def prepare_request(
    profile: CopilotProfile,
    model: CopilotModel,
    messages: list[BaseMessage],
    max_tokens: int,
    kwargs: dict[str, Any],
) -> tuple[str, dict[str, Any], ResponseChunks | ChatChunks]:
    if not isinstance(max_tokens, int) or max_tokens < 16:
        raise CopilotError("invalid_output_budget", 422)
    if model.api != profile.api:
        raise CopilotError("model_protocol_changed", 409)
    budget = min(max_tokens, model.max_output_tokens)
    tools = kwargs.get("tools")
    choice = kwargs.get("tool_choice")
    effort = kwargs.get("reasoning_effort")
    if effort is not None and effort not in model.reasoning_efforts:
        raise CopilotError("unsupported_reasoning_effort", 422)
    if model.api == "openai-responses":
        instructions, items = response_input(messages, model.id, profile.role)
        payload: dict[str, Any] = {
            "model": model.id,
            "input": items,
            "stream": True,
            "store": False,
            "max_output_tokens": budget,
        }
        if model.id.startswith("gpt-"):
            payload["include"] = ["reasoning.encrypted_content"]
        if instructions:
            payload["instructions"] = instructions
        if tools is not None:
            payload["tools"] = tools
        if choice is not None:
            payload["tool_choice"] = choice
        if effort is not None:
            payload["reasoning"] = {"effort": effort}
        return "/responses", payload, ResponseChunks(model.id)
    payload = {
        "model": model.id,
        "messages": chat_input(messages, model.id, profile.role),
        "stream": True,
        "stream_options": {"include_usage": True},
        "store": False,
        "max_completion_tokens": budget,
    }
    if tools is not None:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    key: value for key, value in tool.items() if key != "type"
                },
            }
            for tool in tools
        ]
    elif any(message.get("role") == "tool" for message in payload["messages"]):
        payload["tools"] = []
    if choice is not None:
        payload["tool_choice"] = (
            {"type": "function", "function": {"name": choice["name"]}}
            if isinstance(choice, dict)
            else choice
        )
    if effort is not None:
        payload["reasoning_effort"] = effort
    return "/chat/completions", payload, ChatChunks(model.id)
