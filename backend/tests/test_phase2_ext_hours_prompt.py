"""W3.18 — Phase 2 prompt must teach the LLM that an extended-hours
companion print is a material signal and reasoning_summary must cite it
when the move is ≥ ±1%.

Lock-pattern parallels test_phase2_reasoning_source_ids.py (W3.17): we
inspect the prompt source via `inspect.getsource` so silent prompt
edits in future refactors fail loudly here.
"""

from __future__ import annotations

import inspect

from src.agent.portfolio import phase2_decisions


def _src() -> str:
    return inspect.getsource(
        phase2_decisions.Phase2DecisionsMixin._make_portfolio_decisions
    )


def test_prompt_mentions_extended_hours_companion() -> None:
    src = _src()
    collapsed = " ".join(src.split())
    assert "After-hours" in collapsed or "Extended-Hours" in collapsed, (
        "Phase 2 prompt must reference the W3.18 ext-hours companion "
        "wording so the LLM recognises the Phase 1 'After-hours: $X' / "
        "'Pre-market: $X' lines as a material signal."
    )
    assert "W3.18" in collapsed, (
        "Marker missing — without it future prompt refactors may drift "
        "the rule into an unrelated section."
    )


def test_prompt_specifies_one_percent_materiality_threshold() -> None:
    """The rule must give the LLM a concrete trigger so 'small overnight
    drift' isn't confused with 'material gap'. ±1% matches the PRD."""
    src = _src()
    collapsed = " ".join(src.split())
    has_threshold = (
        "±1%" in collapsed or "1.0%" in collapsed or "± 1%" in collapsed
    )
    assert has_threshold, (
        "W3.18 rule must name an explicit materiality threshold (±1% per "
        "PRD) so the LLM doesn't flag every 5bps drift."
    )


def test_prompt_requires_companion_citation_with_token() -> None:
    """The rule co-locates with W3.17's reasoning_summary citation
    contract: when the LLM names a companion price, it must carry the
    source-ID token. Without this co-location the LLM may quote the
    companion price without provenance."""
    src = _src()
    collapsed = " ".join(src.split())
    # Anchor: the rule must name reasoning_summary and source-ID token
    # in the same paragraph so the W3.17 citation contract extends to
    # the W3.18 companion price.
    assert "reasoning_summary" in collapsed
    assert "source-ID token" in collapsed, (
        "W3.18 rule must reuse the W3.17 'source-ID token' phrasing so "
        "the LLM applies the same citation discipline to companion prices."
    )
