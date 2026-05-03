"""
Centralized LLM client factory - all calls route through Agent Maestro.

Agent Maestro is an Anthropic-API-compatible LLM gateway. Different agents
use different models based on task complexity:

- claude-opus-4-7:    complex reasoning (Planner, Debater, Decisions)
- claude-sonnet-4-6:  balanced (sub-agents, Research, ReAct, Verdict)
- claude-haiku-4-5:   fast/cheap (chat, news sentiment, summaries)

All model assignments can be overridden via env vars (see .env.example).
"""

from __future__ import annotations

import os
from typing import Any

from langchain_anthropic import ChatAnthropic

# ---------------------------------------------------------------------------
# Maestro endpoint configuration
# ---------------------------------------------------------------------------
MAESTRO_BASE_URL = os.getenv(
    "MAESTRO_BASE_URL", "http://localhost:23333/api/anthropic"
)
MAESTRO_AUTH_TOKEN = os.getenv("MAESTRO_AUTH_TOKEN", "Powered by Agent Maestro")


# ---------------------------------------------------------------------------
# Per-role model assignments
# ---------------------------------------------------------------------------
MODELS: dict[str, str] = {
    "deep_planner":         os.getenv("MODEL_DEEP_PLANNER",         "claude-opus-4-7"),
    "sub_financial":        os.getenv("MODEL_SUB_FINANCIAL",        "claude-sonnet-4-6"),
    "sub_technical":        os.getenv("MODEL_SUB_TECHNICAL",        "claude-sonnet-4-6"),
    "sub_news":             os.getenv("MODEL_SUB_NEWS",             "claude-haiku-4-5"),
    "sub_debater":          os.getenv("MODEL_SUB_DEBATER",          "claude-opus-4-7"),
    "simple_chat":          os.getenv("MODEL_SIMPLE_CHAT",          "claude-haiku-4-5"),
    "react_agent":          os.getenv("MODEL_REACT_AGENT",          "claude-sonnet-4-6"),
    "portfolio_research":   os.getenv("MODEL_PORTFOLIO_RESEARCH",   "claude-sonnet-4-6"),
    "portfolio_decisions":  os.getenv("MODEL_PORTFOLIO_DECISIONS",  "claude-opus-4-7"),
    "summary":              os.getenv("MODEL_SUMMARY",              "claude-haiku-4-5"),
    "verdict":              os.getenv("MODEL_VERDICT",              "claude-sonnet-4-6"),
}


def resolve_model(role: str) -> str:
    """Return the configured model name for a role (falls back to simple_chat)."""
    return MODELS.get(role, MODELS["simple_chat"])


def get_llm(
    role: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    streaming: bool = False,
    **kwargs: Any,
) -> ChatAnthropic:
    """
    Get a LangChain ChatAnthropic instance routed through Agent Maestro.

    Args:
        role: Key from MODELS dict. Falls back to "simple_chat" if unknown.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.
        streaming: Enable streaming responses.
        **kwargs: Additional ChatAnthropic args (callbacks, timeout, etc.)
    """
    model = resolve_model(role)
    return ChatAnthropic(
        model_name=model,
        temperature=temperature,
        max_tokens_to_sample=max_tokens,
        streaming=streaming,
        anthropic_api_url=MAESTRO_BASE_URL,
        anthropic_api_key=MAESTRO_AUTH_TOKEN,
        **kwargs,
    )
