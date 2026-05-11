"""Regression: the fallback Phase 2 LLM prompt in `flows.py` must include
an explicit English language directive.

`flows._phase2_for_symbols` is the path taken when the regular portfolio
agent isn't available. Unlike the canonical Phase 2 (`phase2_decisions.py`),
this fallback builds its prompt inline and previously had no language
directive, so DashScope/Qwen defaulted to Chinese — and the resulting
decisions landed Chinese strings in `TradingDecision.reasoning` (a base
field). The frontend then either rendered it as faded English on zh-CN UI
(opacity-0.7 translating state) or as untranslated Chinese under en UI.

Test is source-level so it doesn't require booting the whole portfolio
stack; it asserts the prompt template wired through to `structured.ainvoke`
carries the required directive text.
"""

from __future__ import annotations

from pathlib import Path


def test_fallback_phase2_prompt_includes_english_directive() -> None:
    src = Path("src/agent/portfolio/flows.py").read_text(encoding="utf-8")
    # Look for the language-requirement line. It must mention English so
    # DashScope/Qwen doesn't fall back to Chinese.
    assert "LANGUAGE REQUIREMENT" in src, (
        "flows.py prompt must contain an explicit LANGUAGE REQUIREMENT line "
        "to prevent Chinese leaking into base fields."
    )
    assert "Respond in" in src
    assert "ANALYSIS_OUTPUT_LANG" in src, (
        "flows.py must reference ANALYSIS_OUTPUT_LANG so the directive stays "
        "in lock-step with the pipeline invariant."
    )
