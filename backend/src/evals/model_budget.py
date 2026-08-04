from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.core.utils import extract_token_usage_from_messages, message_content_to_text

from .live_schemas import ModelPricingOverride, ModelUsage
from .pricing import build_model_usage, estimate_max_call_cost


class EvaluationBudgetExceeded(RuntimeError):
    pass


class EvaluationModelBudgetCallback(AsyncCallbackHandler):
    """Stop a multi-step model run before its next unaffordable call."""

    raise_error = True

    def __init__(
        self,
        *,
        role: str,
        provider: str,
        model: str,
        max_cost_usd: float,
        max_output_tokens_per_call: int,
        pricing_overrides: dict[str, ModelPricingOverride],
    ) -> None:
        super().__init__()
        self.role = role
        self.provider = provider
        self.model = model
        self.max_cost_usd = max_cost_usd
        self.max_output_tokens_per_call = max_output_tokens_per_call
        self.pricing_overrides = pricing_overrides
        self.usages: list[ModelUsage] = []

    @property
    def spent_usd(self) -> float:
        return sum(usage.cost_usd for usage in self.usages)

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del serialized, run_id, kwargs
        input_text = "\n".join(
            message_content_to_text(message.content)
            for batch in messages
            for message in batch
        )
        estimated_input_tokens = max(1, math.ceil(len(input_text) / 4))
        reservation = estimate_max_call_cost(
            model=self.model,
            max_input_tokens=estimated_input_tokens,
            max_output_tokens=self.max_output_tokens_per_call,
            overrides=self.pricing_overrides,
        )
        if self.spent_usd + reservation > self.max_cost_usd:
            raise EvaluationBudgetExceeded(
                f"Insufficient target budget before model call: "
                f"requires ${reservation:.6f}, "
                f"remaining ${max(0.0, self.max_cost_usd - self.spent_usd):.6f}"
            )

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        del run_id, kwargs
        messages = [
            generation.message
            for batch in response.generations
            for generation in batch
            if isinstance(generation, ChatGeneration)
        ]
        input_tokens, output_tokens, _ = extract_token_usage_from_messages(messages)
        self.usages.append(
            build_model_usage(
                role=self.role,
                provider=self.provider,
                model=self.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=0,
                overrides=self.pricing_overrides,
            )
        )
