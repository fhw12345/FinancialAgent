"""W3.16-B unit tests — Phase1 prompt carries the TOKEN PRESERVATION RULE.

Background: a real e2e single_symbol run on 2026-05-09 produced a Phase1
research report with zero ``[FH-Q-...]`` / ``[AV-OV-...]`` source-id
tokens, even though the underlying tool calls (W3.2 / W3.3 / W3.4 / W3.5)
correctly emitted ``Source: ... [ID] asof ...`` lines. The LLM treated
those lines as logging noise and stripped them while summarising into the
final markdown report. W3.6 already required Phase 2 thesis bullets to
cite ``[ID]`` tokens, but Phase 2 cannot cite what Phase 1 deletes.

W3.16-B closes the gap by teaching Phase 1 explicitly to preserve and
forward every token end-to-end. These tests pin the prompt wording so
a future refactor cannot silently regress the rule.
"""

from __future__ import annotations

import inspect
import re

from src.agent.portfolio import phase1_research


def _prompt_source() -> str:
    """Snapshot the live ``_analyze_symbol`` source so we lock the wording
    that the running LLM actually sees, not a top-level constant that
    might or might not be referenced."""
    return inspect.getsource(
        phase1_research.Phase1ResearchMixin._analyze_symbol
    )


def _collapsed() -> str:
    """Collapse whitespace runs to a single space — lets the test stay
    insensitive to f-string indentation tweaks while still requiring the
    exact phrasing of each rule."""
    return re.sub(r"\s+", " ", _prompt_source())


# ---------------------------------------------------------------------------
# Header + scope
# ---------------------------------------------------------------------------


def test_token_preservation_rule_header_present() -> None:
    assert "TOKEN PRESERVATION RULE (W3.16)" in _prompt_source()


def test_token_preservation_rule_explains_source_line_shape() -> None:
    """The rule must show the LLM the literal shape it will see in tool
    outputs. Without an example the model treats the line as noise."""
    src = _prompt_source()
    assert "Source: finnhub [FH-Q-NVDA-2026-05-09]" in src


def test_token_preservation_rule_lists_known_id_families() -> None:
    """All four W3.x token families need to be enumerated so the model
    doesn't preserve quote tokens but drop news / insider ones."""
    src = _prompt_source()
    for sample in ("[FH-Q-", "[AV-OV-", "[FH-N-", "[FH-INS-"):
        assert sample in src, f"Missing example token family: {sample}"


# ---------------------------------------------------------------------------
# The five behavioural clauses (preserve / append / multi-source / no
# fabrication / no Source: stripping)
# ---------------------------------------------------------------------------


def test_rule_clause_preserve_verbatim() -> None:
    collapsed = _collapsed()
    assert "Preserve every such token verbatim" in collapsed
    assert "do not rewrite, translate, abbreviate, or strip" in collapsed


def test_rule_clause_append_token_to_citing_sentence() -> None:
    collapsed = _collapsed()
    assert "append the matching `[ID]` token at the end" in collapsed


def test_rule_clause_multi_source_concat() -> None:
    collapsed = _collapsed()
    assert "append both tokens space-separated" in collapsed


def test_rule_clause_no_token_fabrication() -> None:
    collapsed = _collapsed()
    assert "Do NOT invent token strings" in collapsed


def test_rule_clause_dont_delete_source_lines() -> None:
    """The most important clause for the W3.16 fix — without this Phase 1
    keeps stripping ``Source:`` blocks during summarisation."""
    collapsed = _collapsed()
    assert "Never delete a `Source:` line you observed" in collapsed


def test_rule_cross_references_phase2_w3_6() -> None:
    """The rule needs to tell the model *why* it matters. Pointing at
    Phase 2 / W3.6 makes the tradeoff (extra tokens vs. citation chain)
    legible to the model."""
    collapsed = _collapsed()
    assert "Phase 2" in collapsed
    assert "W3.6" in collapsed


# ---------------------------------------------------------------------------
# Ordering: TOKEN PRESERVATION sits AFTER the three earlier prompt rules
# (FIBONACCI / FUNDAMENTAL / INSIDER FRAMING) so the framing rules read
# top-down. A future contributor moving it above the others would be a
# documentation regression even if the wording survives.
# ---------------------------------------------------------------------------


def test_token_preservation_rule_appears_after_insider_framing() -> None:
    src = _prompt_source()
    insider_idx = src.index("INSIDER FRAMING RULE")
    token_idx = src.index("TOKEN PRESERVATION RULE")
    assert insider_idx < token_idx, (
        "TOKEN PRESERVATION should come after INSIDER FRAMING — Phase 1 "
        "rule order has been: technical -> fundamental -> insider -> "
        "provenance, and that order is what the e2e tests in "
        "tests/test_phase1_insider_framing_rule.py implicitly assume."
    )
