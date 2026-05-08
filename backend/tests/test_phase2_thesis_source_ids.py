"""W3.6 source-inspection test — the Phase2 decision prompt must teach
thesis bullets to cite the same source-ID tokens that the W3.2-W3.5
tool wrappers append in their `Source: <provider> [<ID>] asof <iso>`
footnotes.

Without this rule, the LLM may emit thesis bullets with concrete
numbers ("operating margin expanded to 33%") that cannot be traced
back to the tool output that produced the figure — exactly the
hallucinated-thesis failure mode that motivated Wave 3.

This test is prompt-only (it does not exercise the validator). The
deeper AC #1 ("every numeric field under valuation / price_target /
scenarios is a Source object") is a schema migration tracked
separately and will land alongside the frontend ResearchPanel
footnote rendering (W3.7).
"""

from __future__ import annotations

import inspect

from src.agent.portfolio import phase2_decisions


def _src() -> str:
    return inspect.getsource(
        phase2_decisions.Phase2DecisionsMixin._make_portfolio_decisions
    )


def test_prompt_requires_thesis_bullets_to_cite_source_ids() -> None:
    src = _src()
    # Whitespace-collapsed match — the rule wraps across multiple
    # source lines so a literal substring won't match.
    collapsed = " ".join(src.split())
    assert "MUST end with the matching source-ID token" in collapsed, (
        "prompt must require source-ID citation on each thesis bullet"
    )


def test_prompt_shows_concrete_id_token_examples() -> None:
    """Without examples spanning every Wave-3 wrapped tool family,
    the LLM tends to cite only the family it sees most often (quotes)
    and miss fundamentals/news/insider citations."""
    src = _src()
    # One example for each Wave-3 wrapper that ships a source-ID:
    # W3.2 quote (Q), W3.3 fundamentals (OV/CF/BS/EAR/INS),
    # W3.4 news (N), W3.5 insider (INS-on-finnhub).
    assert "[FH-Q-AAPL-2026-05-09]" in src
    assert "[AV-OV-NVDA-2025-09-30]" in src
    assert "[YF-CF-MSFT-2025-12-31]" in src
    assert "[FH-N-AMZN-2026-05-08]" in src
    assert "[FH-INS-TSLA-2026-05-07]" in src


def test_prompt_calls_uncited_thesis_bullets_research_malpractice() -> None:
    """Strong language matters here — the previous research-blocks
    rule (W2.10 base-rate citation) used the same phrasing and the
    LLM took it seriously. Mirror that."""
    src = _src()
    assert "research malpractice" in src
    assert "uncited" in src.lower() or "without a source-ID" in src


def test_prompt_allows_qualitative_bullets_to_skip_citation() -> None:
    """We don't want to force a citation on bullets that are pure
    judgement calls ("the cohort is rate-sensitive") — that would
    push the LLM toward inventing fake source IDs."""
    src = _src()
    assert "the citation is optional" in src or "qualitative judgement" in src


def test_worked_example_thesis_bullets_carry_source_ids() -> None:
    """The worked BUY example must demonstrate the rule, not just
    state it — LLMs follow concrete demonstrations more reliably
    than imperative rules."""
    src = _src()
    # The worked-example thesis section. Each of its 3 bullets ends
    # with a square-bracket source-ID token.
    example_start = src.index('"thesis":')
    example_end = src.index('"valuation":')
    thesis_block = src[example_start:example_end]
    # Three bullets, three closing-bracket tokens. Tolerate
    # whitespace / quote-escaping.
    bracket_tokens = thesis_block.count("[FH-") + thesis_block.count("[AV-") + thesis_block.count("[YF-")
    assert bracket_tokens >= 3, (
        f"worked example must show source-ID tokens on all 3 thesis "
        f"bullets — found {bracket_tokens}"
    )
