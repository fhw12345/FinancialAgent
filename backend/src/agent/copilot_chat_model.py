"""Native role-routed Copilot BaseChatModel (Responses and Chat Completions)."""

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import nullcontext
from typing import Any, cast

import httpx
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    message_chunk_to_message,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field

from ..core.llm_roles import effective_role
from ..services.copilot.context import CopilotProfile, current_profile, probe_model
from ..services.copilot.inference import prepare_request
from ..services.copilot.protocol import HEADERS, CopilotError, check_response
from ..services.copilot.responses import sse_events
from ..services.copilot.service import get_copilot_service


class CopilotChatModel(BaseChatModel):
    role: str = "simple_chat"
    max_tokens: int = Field(default=4096, ge=16, le=200000)
    timeout: float = Field(default=180, gt=0, le=900)
    streaming: bool = False

    @property
    def _llm_type(self) -> str:
        return "github_copilot"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        profile = current_profile(effective_role(self.role))
        return {
            "role": profile.role,
            "provider": "github_copilot",
            "model": profile.model,
            "api": profile.api,
            "routing_revision": profile.routing_revision,
            "account_generation": profile.generation,
        }

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        converted = [
            {
                "type": "function",
                **convert_to_openai_tool(tool)["function"],
                "strict": False,
            }
            for tool in tools
        ]
        if tool_choice in (True, "any", "required"):
            tool_choice = "required"
        elif isinstance(tool_choice, str) and tool_choice not in ("auto", "none"):
            tool_choice = {"type": "function", "name": tool_choice}
        elif isinstance(tool_choice, dict) and "function" in tool_choice:
            tool_choice = {"type": "function", "name": tool_choice["function"]["name"]}
        return self.bind(
            tools=converted,
            **({"tool_choice": tool_choice} if tool_choice is not None else {}),
            **kwargs,
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return asyncio.run(self._agenerate(messages, stop=stop, **kwargs))

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        combined = None
        async for chunk in self._astream(messages, stop=stop, **kwargs):
            combined = chunk if combined is None else combined + chunk
        if combined is None:
            raise CopilotError("empty_model_response")
        message = cast(AIMessage, message_chunk_to_message(combined.message))
        if message.invalid_tool_calls:
            raise CopilotError("invalid_tool_arguments")
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        if stop:
            raise CopilotError("stop_sequences_unsupported", 422)
        service = get_copilot_service()
        role = effective_role(self.role)
        profile = current_profile(role)
        for prior in reversed(messages):
            meta = prior.response_metadata
            if (
                isinstance(prior, AIMessage)
                and meta.get("copilot_role") == role
                and isinstance(meta.get("copilot_generation"), str)
                and isinstance(meta.get("model_name"), str)
                and meta.get("copilot_api")
                in ("openai-responses", "openai-completions")
            ):
                profile = CopilotProfile(
                    meta["model_name"],
                    meta["copilot_generation"],
                    role,
                    meta["copilot_api"],
                    meta.get("routing_revision", 0),
                )
                break
        await service.authorization(generation=profile.generation)
        models = await service.models(refresh=False)
        model = next((model for model in models if model.id == profile.model), None)
        if model is None:
            raise CopilotError("select_an_available_model", 422)
        endpoint, payload, decoder = prepare_request(
            profile, model, messages, kwargs.get("max_tokens", self.max_tokens), kwargs
        )
        rejected_revision: int | None = None
        try:
            for attempt in range(2):
                state = await service.authorization(
                    generation=profile.generation,
                    force=bool(attempt),
                    rejected_revision=rejected_revision,
                )
                headers = {
                    **HEADERS,
                    "Authorization": "Bearer " + state.access_token.get_secret_value(),
                    "X-Initiator": (
                        "user"
                        if messages and isinstance(messages[-1], HumanMessage)
                        else "agent"
                    ),
                    "Openai-Intent": "conversation-edits",
                }
                async with service.client(self.timeout) as client:
                    async with client.stream(
                        "POST", state.base_url + endpoint, headers=headers, json=payload
                    ) as response:
                        if response.status_code == 401 and not attempt:
                            rejected_revision = state.token_revision
                            continue
                        check_response(response)
                        async for event in sse_events(response):
                            if service.store.read().generation != profile.generation:
                                raise CopilotError("session_changed", 409)
                            for chunk in decoder.feed(event):
                                yield self._bound_chunk(chunk, profile)
                        if service.store.read().generation != profile.generation:
                            raise CopilotError("session_changed", 409)
                        for chunk in decoder.finish():
                            yield self._bound_chunk(chunk, profile)
                        return
        except httpx.TimeoutException:
            raise CopilotError("upstream_timeout") from None
        except httpx.TransportError:
            raise CopilotError("stream_connection_failed") from None

    @staticmethod
    def _bound_chunk(chunk: Any, profile: CopilotProfile) -> ChatGenerationChunk:
        if "model_name" in chunk.response_metadata:
            chunk.response_metadata.update(
                {
                    "copilot_generation": profile.generation,
                    "copilot_role": profile.role,
                    "copilot_api": profile.api,
                    "routing_revision": profile.routing_revision,
                }
            )
        return ChatGenerationChunk(message=chunk)


class ConnectionResult(BaseModel):
    connected: bool


async def test_connection(
    model_id: str | None = None, role: str = "simple_chat"
) -> dict[str, Any]:
    """One explicit bounded test, optionally for a model without changing routing."""
    await get_copilot_service().models(refresh=False)
    with probe_model(model_id, role) if model_id else nullcontext():
        profile = current_profile(role)
        llm = CopilotChatModel(role=role, max_tokens=512, timeout=60)
        result = await llm.with_structured_output(ConnectionResult).ainvoke(
            "Connection check only. Return connected=true using the supplied tool. Do not call any other tools."
        )
        validated = ConnectionResult.model_validate(result)
        if not validated.connected:
            raise CopilotError("connection_check_failed")
        return {
            "connected": True,
            "model": profile.model,
            "role": role,
            "protocol": profile.api,
            "routing_revision": profile.routing_revision,
        }
