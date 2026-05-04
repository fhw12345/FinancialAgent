"""
Centralized LLM client factory - all calls route through Agent Maestro.

Agent Maestro is an Anthropic-API-compatible LLM gateway exposing Claude,
GPT, and Gemini families. Roles are assigned across vendors for diversity
(notably: debater uses a non-Claude model so adversarial debate isn't
self-correlated).

All model assignments can be overridden via env vars (see .env.example).
"""

from __future__ import annotations

import os
from typing import Any

from langchain_anthropic import ChatAnthropic

# ---------------------------------------------------------------------------
# Maestro endpoint configuration
# ---------------------------------------------------------------------------
MAESTRO_BASE_URL = os.getenv("MAESTRO_BASE_URL", "http://localhost:23333/api/anthropic")
MAESTRO_AUTH_TOKEN = os.getenv("MAESTRO_AUTH_TOKEN", "Powered by Agent Maestro")


# ---------------------------------------------------------------------------
# Per-role model assignments
# ---------------------------------------------------------------------------
MODELS: dict[str, str] = {
    # — Anthropic Opus 4.7 family — long-context for tool-heavy + deep reasoning
    # 1m-internal: 935k context window (best for ReAct + 24 tools + history)
    "deep_planner": os.getenv("MODEL_DEEP_PLANNER", "claude-opus-4.7-xhigh"),
    "react_agent": os.getenv("MODEL_REACT_AGENT", "claude-opus-4.7-1m-internal"),
    "portfolio_decisions": os.getenv("MODEL_PORTFOLIO_DECISIONS", "claude-opus-4.7-xhigh"),
    "verdict": os.getenv("MODEL_VERDICT", "claude-opus-4.7-xhigh"),
    "sub_technical": os.getenv("MODEL_SUB_TECHNICAL", "claude-opus-4.7"),
    "simple_chat": os.getenv("MODEL_SIMPLE_CHAT", "claude-haiku-4.5"),
    # — GPT-5.5 — best OpenAI flagship for structured extraction
    "sub_financial": os.getenv("MODEL_SUB_FINANCIAL", "gpt-5.5"),
    "portfolio_research": os.getenv("MODEL_PORTFOLIO_RESEARCH", "gpt-5.5"),
    # — Gemini 3.1 Pro — cross-vendor diversity for adversarial debate
    "sub_debater": os.getenv("MODEL_SUB_DEBATER", "gemini-3.1-pro-preview"),
    "sub_news": os.getenv("MODEL_SUB_NEWS", "gemini-3.1-pro-preview"),
    "summary": os.getenv("MODEL_SUMMARY", "gemini-3.1-pro-preview"),
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

    Maestro accepts non-Anthropic model IDs (gpt-*, gemini-*) over the
    Anthropic-compatible endpoint and proxies to the underlying vendor.

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
