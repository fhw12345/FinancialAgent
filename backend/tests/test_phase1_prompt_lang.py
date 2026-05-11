"""W2.3+W2.4 — Phase1 prompt language switch via PHASE1_PROMPT_LANG env.

Default flipped from zh-CN to English so the analysis pipeline emits English
and the persistence translator has an unambiguous English -> zh-CN direction
to feed DashScope. `PHASE1_PROMPT_LANG=zh` remains as an emergency override.
"""

from __future__ import annotations

import os

import pytest

from src.agent.portfolio.phase1_research import _phase1_language_directive


@pytest.fixture(autouse=True)
def _restore_env():
    saved = os.environ.get("PHASE1_PROMPT_LANG")
    yield
    if saved is None:
        os.environ.pop("PHASE1_PROMPT_LANG", None)
    else:
        os.environ["PHASE1_PROMPT_LANG"] = saved


def test_default_is_english() -> None:
    os.environ.pop("PHASE1_PROMPT_LANG", None)
    out = _phase1_language_directive()
    assert "Respond in English" in out
    assert "Simplified Chinese" not in out
    assert "ticker symbols" in out  # preserve verbatim guidance


def test_en_explicit_returns_english() -> None:
    os.environ["PHASE1_PROMPT_LANG"] = "en"
    out = _phase1_language_directive()
    assert "Respond in English" in out
    assert "Simplified Chinese" not in out


def test_en_us_also_returns_english() -> None:
    os.environ["PHASE1_PROMPT_LANG"] = "en-US"
    out = _phase1_language_directive()
    assert "Respond in English" in out


def test_zh_override_returns_chinese() -> None:
    os.environ["PHASE1_PROMPT_LANG"] = "zh"
    out = _phase1_language_directive()
    assert "Simplified Chinese" in out
    assert "简体中文" in out


def test_zh_cn_override_returns_chinese() -> None:
    os.environ["PHASE1_PROMPT_LANG"] = "zh-CN"
    out = _phase1_language_directive()
    assert "Simplified Chinese" in out


def test_garbage_value_falls_back_to_english() -> None:
    os.environ["PHASE1_PROMPT_LANG"] = "klingon"
    out = _phase1_language_directive()
    # Anything not starting with "zh" defaults to en — the pipeline
    # invariant locks the analysis layer to English.
    assert "Respond in English" in out
    assert "Simplified Chinese" not in out


def test_phase1_passes_language_to_react_agent() -> None:
    """Regression: phase1_research.py must pass `language=ANALYSIS_OUTPUT_LANG`
    to `react_agent.ainvoke`. Without it the agent defaults to
    `DEFAULT_LANGUAGE = "zh-CN"` and appends a "Respond in Simplified Chinese"
    directive to the user message tail, which overrides Phase 1's own English
    directive and causes Chinese to leak into the analysis-output base field.
    """
    import ast
    from pathlib import Path

    src = Path("src/agent/portfolio/phase1_research.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # match `<something>.react_agent.ainvoke(...)` or
        # `self.react_agent.ainvoke(...)`
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "ainvoke"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "react_agent"
        ):
            continue
        kw_names = {kw.arg for kw in node.keywords}
        assert "language" in kw_names, (
            "react_agent.ainvoke() in phase1_research.py must pass "
            "language=ANALYSIS_OUTPUT_LANG to override the zh-CN default "
            "injected by langgraph_react_agent.ainvoke."
        )
        # value should be the ANALYSIS_OUTPUT_LANG name reference, not a
        # string literal — keep the invariant single-sourced.
        lang_kw = next(kw for kw in node.keywords if kw.arg == "language")
        assert isinstance(lang_kw.value, ast.Name) and (
            lang_kw.value.id == "ANALYSIS_OUTPUT_LANG"
        ), "language= must reference ANALYSIS_OUTPUT_LANG, not a hardcoded literal"
        found = True

    assert found, "no react_agent.ainvoke() call found in phase1_research.py"
