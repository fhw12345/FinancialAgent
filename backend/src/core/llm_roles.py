"""Shared model-role catalog and narrow native scopes for reused ReAct graphs."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

ROLE_MODEL_FIELDS = {
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
    "eval_judge": "model_eval_judge",
    # Preserve non-native defaults while permitting independent native routing.
    "translation": "model_verdict",
    "consistency_check": "model_simple_chat",
}

ROLE_LABELS = {
    "router": "Routing / symbol clarification",
    "simple_chat": "Simple chat",
    "react_agent": "ReAct tool analysis",
    "portfolio_research": "Portfolio Phase 1 research",
    "portfolio_decisions": "Portfolio Phase 2 decisions",
    "sub_technical": "Deep technical research",
    "sub_news": "Deep news research",
    "sub_financial": "Deep financial research",
    "sub_debater": "Deep adversarial review",
    "verdict": "Deep final verdict",
    "summary": "Context summary",
    "translation": "Display translation",
    "consistency_check": "Research consistency check",
    "eval_judge": "Evaluation judge",
    "deep_planner": "Deep planner (reserved by current fixed graph)",
}

BALANCED_MODELS = {
    **dict.fromkeys(
        ("router", "simple_chat", "summary", "translation", "consistency_check"),
        "gpt-5.4-mini",
    ),
    **dict.fromkeys(
        (
            "react_agent",
            "portfolio_research",
            "sub_financial",
            "sub_technical",
            "deep_planner",
        ),
        "gpt-5.6-sol",
    ),
    "sub_news": "gemini-3.8-flash",
    "sub_debater": "grok-4.6",
    "portfolio_decisions": "gpt-6-astra",
    "verdict": "gpt-6-astra",
    "eval_judge": "gpt-5.4",
}

_scopes: ContextVar[tuple[tuple[str, str], ...]] = ContextVar(
    "native_role_scopes", default=()
)


def effective_role(role: str) -> str:
    for source, target in reversed(_scopes.get()):
        if source == role:
            return target
    return role


@contextmanager
def model_role_scope(source: str, target: str) -> Iterator[None]:
    if source not in ROLE_MODEL_FIELDS or target not in ROLE_MODEL_FIELDS:
        raise ValueError("Unknown model role")
    token = _scopes.set((*_scopes.get(), (source, target)))
    try:
        yield
    finally:
        _scopes.reset(token)
