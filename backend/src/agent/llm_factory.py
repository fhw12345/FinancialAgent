"""Centralized role-based LLM factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from langchain_anthropic import ChatAnthropic

from ..core.config import Settings, get_settings
from ..core.exceptions import ConfigurationError

LLMProvider = Literal["maestro", "anthropic", "copilot_reverse"]

ROLE_MODEL_FIELDS: dict[str, str] = {
    "deep_planner": "model_deep_planner",
    "react_agent": "model_react_agent",
    "portfolio_decisions": "model_portfolio_decisions",
    "verdict": "model_verdict",
    "sub_technical": "model_sub_technical",
    "simple_chat": "model_simple_chat",
    "sub_financial": "model_sub_financial",
    "portfolio_research": "model_portfolio_research",
    "sub_debater": "model_sub_debater",
    "sub_news": "model_sub_news",
    "summary": "model_summary",
    "router": "model_router",
}

COPILOT_REVERSE_MODELS: dict[str, str] = {
    "deep_planner": "claude-opus-4.8",
    "react_agent": "claude-sonnet-5",
    "portfolio_decisions": "claude-opus-4.8",
    "verdict": "claude-opus-4.8",
    "sub_technical": "claude-sonnet-5",
    "simple_chat": "claude-haiku-4.5",
    "sub_financial": "gpt-5.6-sol",
    "portfolio_research": "gpt-5.6-sol",
    "sub_debater": "gpt-5.6-sol",
    "sub_news": "claude-sonnet-5",
    "summary": "gpt-5.4-mini",
    "router": "claude-haiku-4.5",
}


@dataclass(frozen=True)
class LLMRoute:
    """Resolved endpoint and model for one LLM request."""

    provider: LLMProvider
    base_url: str
    api_key: str
    model: str


def _role_field(role: str) -> str:
    return ROLE_MODEL_FIELDS.get(role, ROLE_MODEL_FIELDS["simple_chat"])


def resolve_model(role: str, settings: Settings | None = None) -> str:
    """Resolve a role to a model for the selected provider."""
    settings = settings or get_settings()

    if settings.llm_provider == "maestro":
        return str(getattr(settings, _role_field(role)))

    if settings.llm_provider == "anthropic":
        if not settings.anthropic_model:
            raise ConfigurationError(
                "ANTHROPIC_MODEL is required when LLM_PROVIDER=anthropic"
            )
        return settings.anthropic_model

    if settings.copilot_reverse_model:
        return settings.copilot_reverse_model
    return COPILOT_REVERSE_MODELS.get(
        role,
        COPILOT_REVERSE_MODELS["simple_chat"],
    )


def resolve_route(
    role: str,
    settings: Settings | None = None,
) -> LLMRoute:
    """Resolve provider, endpoint, credentials, and model."""
    settings = settings or get_settings()
    provider = settings.llm_provider
    model = resolve_model(role, settings)

    if provider == "maestro":
        return LLMRoute(
            provider=provider,
            base_url=settings.maestro_base_url,
            api_key=settings.maestro_auth_token,
            model=model,
        )

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )
        return LLMRoute(
            provider=provider,
            base_url=settings.anthropic_base_url,
            api_key=settings.anthropic_api_key,
            model=model,
        )

    return LLMRoute(
        provider=provider,
        base_url=settings.copilot_reverse_base_url,
        api_key=settings.copilot_reverse_auth_token,
        model=model,
    )


def get_role_models(settings: Settings | None = None) -> dict[str, str]:
    """Return the active model assignment for every role."""
    settings = settings or get_settings()
    return {role: resolve_model(role, settings) for role in ROLE_MODEL_FIELDS}


def get_llm(
    role: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    streaming: bool = False,
    **kwargs: Any,
) -> ChatAnthropic:
    """Create an Anthropic-compatible client for the selected provider."""
    route = resolve_route(role)
    return ChatAnthropic(
        model_name=route.model,
        temperature=temperature,
        max_tokens_to_sample=max_tokens,
        streaming=streaming,
        anthropic_api_url=route.base_url.rstrip("/"),
        anthropic_api_key=route.api_key,
        **kwargs,
    )
