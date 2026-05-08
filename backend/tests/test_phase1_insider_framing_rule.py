"""W3.11 — Phase1 prompt encodes the discretionary cluster rule.

The prompt's INSIDER FRAMING RULE pins three conditions for bearish
framing (cluster≥3 / >5% of holdings / breaks 12-mo pattern) and adds
the PLAN-TYPE OVERRIDE that locks 10b5-1 transactions out of
discretionary-bearish framing entirely. PRD AC #4 is asserted directly:
"a `plan_type=10b5-1, plan_adopted=2024-03-01` insider tx with current
date 2025-01-01 is **not** allowed to be cited as discretionary
bearish."

We assert against the source of `_analyze_symbol` because the prompt
is composed inline as an f-string — there is no exported template
constant to read. The rule wraps across source lines, so checks
collapse whitespace before substring testing.
"""

from __future__ import annotations

import inspect

from src.agent.portfolio.phase1_research import Phase1ResearchMixin


def _prompt_src() -> str:
    return inspect.getsource(Phase1ResearchMixin._analyze_symbol)


def _collapsed() -> str:
    return " ".join(_prompt_src().split())


class TestW311PromptRule:
    def test_insider_framing_rule_header_present(self) -> None:
        assert "INSIDER FRAMING RULE (W3.11)" in _prompt_src()

    def test_three_conditions_listed(self) -> None:
        c = _collapsed()
        assert "Cluster size" in c
        assert "Material size" in c
        assert "Breaks the 12-month pattern" in c

    def test_cluster_size_threshold_at_least_3_in_30_days(self) -> None:
        c = _collapsed()
        assert "at least 3 separate sell transactions" in c
        assert "30-day window" in c

    def test_material_size_threshold_5pct(self) -> None:
        c = _collapsed()
        assert "pct_of_holdings_after` > 0.05" in c or "pct_of_holdings_after > 0.05" in c

    def test_breaks_12mo_pattern_clause(self) -> None:
        c = _collapsed()
        assert "last_12mo" in c
        assert "first burst of discretionary activity" in c

    def test_all_three_conditions_required_conjunction(self) -> None:
        # The rule must require ALL THREE, not any-of.
        c = _collapsed()
        assert "ALL THREE" in c

    def test_10b5_1_override_locks_out_bearish_framing(self) -> None:
        # PRD AC #4: 10b5-1 cannot be cited as discretionary bearish.
        c = _collapsed()
        assert "PLAN-TYPE OVERRIDE" in c
        assert "10b5-1" in c
        assert "MUST NOT be cited as discretionary bearish" in c

    def test_neutral_framing_for_10b5_1(self) -> None:
        c = _collapsed()
        assert "treat the transaction as neutral" in c

    def test_missing_plan_type_defaults_to_neutral(self) -> None:
        # When SEC fetch fails, plan_type is absent — must NOT be
        # silently treated as discretionary.
        c = _collapsed()
        assert "default to neutral framing" in c

    def test_single_sell_does_not_establish_cluster(self) -> None:
        c = _collapsed()
        assert "single sell" in c
        assert "does not establish a cluster" in c

    def test_routine_liquidity_carve_out(self) -> None:
        # Sub-5% sells must be carved out as routine.
        c = _collapsed()
        assert "routine liquidity" in c or "tax events" in c

    def test_discretionary_and_unknown_only_with_three_conditions(self) -> None:
        c = _collapsed()
        assert "`discretionary` and `unknown` plan types may contribute" in c

    def test_rule_appears_after_w1_rules(self) -> None:
        # Ordering: keep the W3.11 block after the existing W1 rules so
        # the LLM reads them in chronological / wave order.
        src = _prompt_src()
        i_w1 = src.find("FUNDAMENTAL DATA RULE (W1.5-W1.8)")
        i_w311 = src.find("INSIDER FRAMING RULE (W3.11)")
        assert i_w1 != -1 and i_w311 != -1
        assert i_w311 > i_w1
