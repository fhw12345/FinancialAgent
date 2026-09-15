"""Native Responses BaseChatModel: no bridge and no coding-agent tool authority."""

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
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

from ..services.copilot.context import CopilotProfile, current_profile
from ..services.copilot.protocol import HEADERS, CopilotError, check_response
from ..services.copilot.responses import ResponseChunks, response_input, sse_events
from ..services.copilot.service import get_copilot_service


class CopilotChatModel(BaseChatModel):
    role: str = "simple_chat"
    max_tokens: int = Field(default=4096, ge=16, le=200000)
    timeout: float = Field(default=180, gt=0, le=900)
    streaming: bool = False

    @property
    def _llm_type(self) -> str:
        return "github_copilot_responses"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"role": self.role, "provider": "github_copilot"}

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        converted = []
        for tool in tools:
            function = convert_to_openai_tool(tool)["function"]
            converted.append({"type": "function", **function, "strict": False})
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
        profile = current_profile()
        # LangGraph may run successive tool-loop nodes in different tasks.
        # Carry the binding with the native AI message as well as ContextVar.
        for prior in reversed(messages):
            generation = prior.response_metadata.get("copilot_generation")
            model_name = prior.response_metadata.get("model_name")
            if (
                isinstance(prior, AIMessage)
                and isinstance(generation, str)
                and isinstance(model_name, str)
            ):
                profile = CopilotProfile(model_name, generation)
                break
        await service.authorization(generation=profile.generation)
        models = await service.models(refresh=False)
        model = next((model for model in models if model.id == profile.model), None)
        if model is None:
            raise CopilotError("select_an_available_model", 422)
        instructions, inputs = response_input(messages, profile.model)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        if not isinstance(max_tokens, int) or max_tokens < 16:
            raise CopilotError("invalid_output_budget", 422)
        payload: dict[str, Any] = {
            "model": profile.model,
            "input": inputs,
            "stream": True,
            "store": False,
            "max_output_tokens": min(max_tokens, model.max_output_tokens),
            "include": ["reasoning.encrypted_content"],
        }
        if instructions:
            payload["instructions"] = instructions
        for key in ("tools", "tool_choice"):
            if key in kwargs:
                payload[key] = kwargs[key]
        # Native GPT reasoning models do not accept the app's temperature=0.7.
        # Do not send that unsupported sampling parameter or silently emulate it.
        decoder = ResponseChunks(profile.model)
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
                        "POST",
                        state.base_url + "/responses",
                        headers=headers,
                        json=payload,
                    ) as response:
                        if response.status_code == 401 and not attempt:
                            rejected_revision = state.token_revision
                            continue  # No response/output consumed; one token refresh only.
                        check_response(response)
                        async for event in sse_events(response):
                            if service.store.read().generation != profile.generation:
                                raise CopilotError("session_changed", 409)
                            for chunk in decoder.feed(event):
                                if "model_name" in chunk.response_metadata:
                                    chunk.response_metadata["copilot_generation"] = (
                                        profile.generation
                                    )
                                yield ChatGenerationChunk(message=chunk)
                        if not decoder.completed:
                            raise CopilotError("stream_ended_without_completion")
                        return
        except httpx.TimeoutException:
            raise CopilotError("upstream_timeout") from None
        except httpx.TransportError:
            raise CopilotError("stream_connection_failed") from None


class ConnectionResult(BaseModel):
    connected: bool


async def test_connection() -> dict[str, Any]:
    """One explicit, small-budget request; verifies native structured output."""
    profile = current_profile()
    llm = CopilotChatModel(max_tokens=256, timeout=45)
    result = await llm.with_structured_output(ConnectionResult).ainvoke(
        "Connection check only. Return connected=true using the supplied tool. Do not call any other tools."
    )
    validated = ConnectionResult.model_validate(result)
    if not validated.connected:
        raise CopilotError("connection_check_failed")
    return {
        "connected": True,
        "model": profile.model,
        "protocol": "openai-responses",
    }
