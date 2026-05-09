"""W3.17 source-inspection test — the Phase2 decision prompt must
teach `reasoning_summary` to cite the same source-ID tokens that
W3.6 already requires of `thesis` bullets.

Backstory: W3.6 (test_phase2_thesis_source_ids.py) locked the rule
that each thesis bullet citing a number must end with the matching
`[FH-Q-...]` / `[AV-OV-...]` / `[YF-...]` token. But the schema makes
``thesis: list[str] | None = None`` — HOLD decisions are allowed to
skip thesis entirely and route their narrative into the required
``reasoning_summary`` field. The 2026-05-09 NVDA HOLD run did exactly
that: reasoning named $217.80 (price), RSI 65.86 (technical), Fwd P/E
19 (fundamental), $269 (target), 9.24% (P&L), 83% (concentration),
1.56 (beta) — every number lifted from Phase 1 full_research — yet
the text carried zero `[ID]` tokens because the prompt simply never
said reasoning had the same obligation.

These tests pin a parallel rule on `reasoning_summary` so HOLD
decisions can no longer route around the citation contract. We do NOT
require qualitative phrases ("digestion phase", "support holds") to
cite — same flexibility carve-out as W3.6.

Like the W3.6 test, this is prompt-only (does not exercise the
validator). The integration test
``test_single_symbol_flow_real.py::test_phase2_decision_cites_at_least_one_token``
flips back from xfail to a regular assertion once this rule lands and
a fresh single_symbol run produces a token-bearing reasoning.
"""

from __future__ import annotations

import inspect

from src.agent.portfolio import phase2_decisions


def _src() -> str:
    return inspect.getsource(
        phase2_decisions.Phase2DecisionsMixin._make_portfolio_decisions
    )


def _collapsed() -> str:
    return " ".join(_src().split())


def test_prompt_requires_reasoning_summary_to_cite_source_ids() -> None:
    """The W3.17 parallel of the W3.6 thesis rule. We don't lock
    *exactly* the W3.6 phrasing because reasoning is a single string,
    not a bullet list — but the imperative ('MUST') and the citation
    target ('source-ID token') must be present and clearly tied to
    `reasoning_summary`, AND the rule must apply to numbers lifted
    from Phase 1 research, not just the entry/stop/take levels that
    the pre-existing W2.6 line already covers."""
    src = _src()
    collapsed = " ".join(src.split())
    # The pre-existing W2.6 wording covers entry/stop/take levels
    # only ('cite the specific tool-derived levels you used for ALL
    # THREE prices') — that is NOT the W3.17 obligation. W3.17 needs
    # a rule that scopes citation to ANY number lifted from Phase 1
    # research / full_research, including ratios / RSI / P/E / %.
    #
    # We check for the broader scope by requiring the rule to live
    # in the same paragraph that mentions either "source-ID token"
    # or one of the W3.16-B token-family example prefixes — that
    # guarantees the rule talks about provenance tokens, not just
    # which level number to anchor.
    assert "reasoning_summary" in collapsed
    # The reasoning_summary section must reference source-ID tokens,
    # not only the W2.6 'tool-derived levels' phrasing.
    rs_idx = src.find("reasoning_summary")
    # Walk forward through every reasoning_summary mention and
    # require AT LEAST ONE to sit within ~600 chars of a source-ID
    # token reference. This anchors the W3.17 rule next to the
    # thesis-style provenance language rather than the W2.6
    # entry/stop/take instruction.
    found_provenance_link = False
    while rs_idx != -1:
        window = src[rs_idx : rs_idx + 600]
        # Use the literal phrase 'source-ID token' as the anchor —
        # NOT just `[FH-` etc, because the worked example's
        # `"reasoning_summary": "..."` line sits ~200 chars before
        # the example's `"thesis": [` array which has tokens of its
        # own. Looking for token literals inside that 600-char
        # window would false-positive on the example, missing the
        # actual W3.17 rule absence.
        if "source-ID token" in window:
            found_provenance_link = True
            break
        rs_idx = src.find("reasoning_summary", rs_idx + 1)
    assert found_provenance_link, (
        "Phase 2 prompt must require reasoning_summary to cite "
        "source-ID tokens (not only entry/stop/take levels) when it "
        "lifts numbers from Phase 1 research. W3.17 — without this, "
        "HOLD decisions whose narrative rides in reasoning route "
        "around the W3.6 thesis citation contract."
    )


def test_prompt_explains_reasoning_citation_motivation() -> None:
    """The rule must tell the LLM *why* — pointing at HOLD decisions
    leaving thesis null and routing narrative into reasoning instead.
    Without the motivation, prompt edits in this section tend to drift
    on subsequent refactors."""
    collapsed = _collapsed()
    # Either explicit "HOLD" mention or "thesis null" / "thesis is
    # null" / "without a thesis" framing — any of these makes the
    # carve-out legible to the LLM.
    has_hold_framing = (
        "HOLD" in collapsed
        and ("reasoning_summary" in collapsed)
    )
    assert has_hold_framing, (
        "Reasoning-citation rule must explain that HOLD decisions "
        "without a thesis route narrative into reasoning_summary, "
        "so the LLM understands the parallel obligation."
    )


def test_prompt_allows_qualitative_reasoning_phrases_to_skip_citation() -> None:
    """Same flexibility as W3.6: pure qualitative phrases ('the
    breakout looks tired', 'wait for digestion') don't need citations
    — we don't want the LLM inventing tokens to satisfy a blanket
    requirement."""
    src = _src()
    collapsed = " ".join(src.split())
    # Either an explicit carve-out for reasoning, or a single
    # carve-out clause that visibly applies to both fields.
    assert (
        "qualitative" in collapsed
    ), "Reasoning rule must preserve the qualitative-phrase carve-out."


def test_worked_example_reasoning_carries_source_ids() -> None:
    """The W3.6 worked example demonstrates thesis citation; W3.17
    requires the same example's `reasoning_summary` to carry at least
    one `[ID]` token so the LLM sees the rule applied, not just stated.
    Concrete demonstration outweighs imperative wording for LLMs."""
    src = _src()
    # Find the worked example's reasoning_summary value. The example
    # starts at `"symbol": "EXMP"` and the reasoning_summary value is
    # a single line ending before the `"thesis":` line.
    example_start = src.index('"symbol": "EXMP"')
    thesis_start = src.index('"thesis":', example_start)
    example_reasoning_block = src[example_start:thesis_start]
    bracket_tokens = (
        example_reasoning_block.count("[FH-")
        + example_reasoning_block.count("[AV-")
        + example_reasoning_block.count("[YF-")
    )
    assert bracket_tokens >= 1, (
        "Worked example's reasoning_summary must demonstrate the rule "
        "by carrying at least one source-ID token — found "
        f"{bracket_tokens}. LLMs follow concrete demonstrations more "
        "reliably than imperative rules (same lesson as W3.6 thesis)."
    )


def test_reasoning_rule_appears_alongside_thesis_rule() -> None:
    """Co-locating the two rules makes the parallel obvious to a
    contributor reading the prompt top-to-bottom; if a future edit
    splits them across distant sections the LLM may apply the rule
    inconsistently. We require the reasoning rule to sit either
    just before or just after the thesis rule, both inside the
    'Structured Research Blocks' section that the W3.6 rule lives in."""
    src = _src()
    # Anchor on a phrase that survives the f-string's mid-paragraph
    # newlines — `MUST end with the matching source-ID\n  token in
    # square brackets` wraps in the literal source. Use the W3.6
    # malpractice line which sits inside the same rule and is on a
    # single line.
    thesis_rule_idx = src.index("research malpractice")
    # Window covers ±1200 chars around the thesis rule's malpractice
    # phrase — ample room for an adjacent reasoning rule (above or
    # below) but tight enough to catch a future edit that pushes the
    # reasoning rule into a far-away section like 'Numeric
    # Derivation' or 'Important Considerations'.
    window_start = max(0, thesis_rule_idx - 1200)
    window_end = min(len(src), thesis_rule_idx + 1200)
    nearby_window = src[window_start:window_end]
    # Look for a reasoning-citation rule (not just any
    # `reasoning_summary` mention — the word appears in unrelated
    # paragraphs too). Anchor on the W3.17 marker AND a co-mention of
    # `reasoning_summary` so the test fails if a future edit either
    # removes the marker or moves it away from the thesis rule.
    has_w317_marker = "W3.17" in nearby_window
    has_reasoning_mention = "reasoning_summary" in nearby_window
    assert has_w317_marker and has_reasoning_mention, (
        "Reasoning-citation rule must sit in/near the Structured "
        "Research Blocks section so it reads as a parallel to the "
        "thesis rule, not as an unrelated paragraph. Expected the "
        "W3.17 marker AND `reasoning_summary` within ±1200 chars of "
        "the thesis-rule malpractice phrase; got "
        f"W3.17={has_w317_marker}, reasoning_summary="
        f"{has_reasoning_mention}."
    )
