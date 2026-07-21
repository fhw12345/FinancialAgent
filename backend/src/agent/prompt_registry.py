"""Stable prompt identities and versions used by durable runs and evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: str
    version: int
    template: str = ""
    tags: tuple[str, ...] = ()

    @property
    def versioned_id(self) -> str:
        return f"{self.prompt_id}@{self.version}"

    def render(self, **context: Any) -> str:
        if not self.template:
            raise ValueError(f"Prompt {self.versioned_id} has no registered template")
        return self.template.format(**context)


ROUTER_TEMPLATE = """Classify this Financial Agent request into exactly one flow.

v2: direct conversational answer; no current market data or tools needed.
v3: tool-using financial analysis, current data, news, fundamentals, or technical analysis.
v4-deep: explicitly requests comprehensive/deep investment research, multi-angle analysis, or adversarial debate.

Selected symbol from UI: {current_symbol}
User message: {message}
"""

_PROMPTS = {
    spec.prompt_id: spec
    for spec in (PromptSpec("router", 1, ROUTER_TEMPLATE, ("routing", "structured")),)
}


def get_prompt(prompt_id: str) -> PromptSpec:
    try:
        return _PROMPTS[prompt_id]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt id: {prompt_id}") from exc


def render_prompt(prompt_id: str, **context: Any) -> str:
    return get_prompt(prompt_id).render(**context)


def prompt_registry_snapshot() -> dict[str, str]:
    return {
        prompt_id: spec.versioned_id for prompt_id, spec in sorted(_PROMPTS.items())
    }
