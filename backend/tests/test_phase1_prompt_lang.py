"""W2.3+W2.4 — Phase1 prompt language switch via PHASE1_PROMPT_LANG env."""

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


def test_default_is_simplified_chinese() -> None:
    os.environ.pop("PHASE1_PROMPT_LANG", None)
    out = _phase1_language_directive()
    assert "Simplified Chinese" in out
    assert "简体中文" in out


def test_zh_explicit_returns_chinese() -> None:
    os.environ["PHASE1_PROMPT_LANG"] = "zh"
    out = _phase1_language_directive()
    assert "Simplified Chinese" in out


def test_en_returns_english_directive() -> None:
    os.environ["PHASE1_PROMPT_LANG"] = "en"
    out = _phase1_language_directive()
    assert "Respond in English" in out
    assert "Simplified Chinese" not in out
    assert "ticker symbols" in out  # preserve verbatim guidance


def test_en_us_also_returns_english() -> None:
    os.environ["PHASE1_PROMPT_LANG"] = "en-US"
    out = _phase1_language_directive()
    assert "Respond in English" in out


def test_garbage_value_falls_back_to_chinese() -> None:
    os.environ["PHASE1_PROMPT_LANG"] = "klingon"
    out = _phase1_language_directive()
    # Anything not starting with "en" defaults to zh — safer than
    # silently mis-language for an unknown lang code.
    assert "Simplified Chinese" in out
