"""Tests for bounded multi-turn Deep Research context."""

from src.agent.deep_research_context import DeepResearchContext


def test_extracts_prior_report_horizon_risk_and_constraints():
    context = DeepResearchContext.from_history(
        current_request="Now challenge that thesis and focus on downside.",
        conversation_history=[
            {
                "role": "user",
                "content": "Analyze SKHY over a 6 month horizon with moderate risk and focus on valuation.",
            },
            {
                "role": "assistant",
                "content": "SKHY has a bullish thesis based on improving HBM demand.",
            },
        ],
    )

    assert context.confirmed_symbol == "SKHY"
    assert context.investment_horizon == "6 months"
    assert context.risk_tolerance == "moderate"
    assert context.constraints == (
        "valuation_focus",
        "downside_focus",
        "adversarial_review",
    )
    assert context.previous_assistant_report is not None
    assert "bullish thesis" in context.previous_assistant_report
    assert context.allows_symbol_reuse is True


def test_chinese_horizon_and_risk_are_extracted():
    context = DeepResearchContext.from_history(
        current_request="沿用之前的约束，继续分析下行风险。",
        conversation_history=[
            {
                "role": "user",
                "content": "请按12个月周期，以稳健风险偏好分析 AAPL。",
            },
            {"role": "assistant", "content": "AAPL 初步结论为持有。"},
        ],
    )

    assert context.confirmed_symbol == "AAPL"
    assert context.investment_horizon == "12个月"
    assert context.risk_tolerance == "moderate"
    assert "downside_focus" in context.constraints


def test_context_is_bounded_and_marks_truncation():
    history = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": "X" * 2000}
        for index in range(10)
    ]

    context = DeepResearchContext.from_history(
        current_request="Continue the same analysis.",
        conversation_history=history,
    )

    assert len(context.relevant_turns) <= 6
    assert sum(len(turn.content) for turn in context.relevant_turns) <= 6000
    assert context.truncated is True
    assert len(context.render(symbol="AAPL")) < 8000


def test_total_budget_preserves_newest_turns():
    history = [
        {
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"MARKER_{index} {'MSFT' if index < 4 else 'AAPL'} "
            + ("X" * 1300),
        }
        for index in range(6)
    ]

    context = DeepResearchContext.from_history(
        current_request="Continue and challenge that thesis.",
        conversation_history=history,
    )

    assert all("MARKER_0" not in turn.content for turn in context.relevant_turns)
    assert "MARKER_5" in context.relevant_turns[-1].content
    assert context.previous_assistant_report is not None
    assert "MARKER_5" in context.previous_assistant_report
    assert context.confirmed_symbol == "AAPL"
    assert context.truncated is True


def test_latest_symbol_in_same_turn_wins():
    context = DeepResearchContext.from_history(
        current_request="Continue with that comparison.",
        conversation_history=[
            {
                "role": "user",
                "content": (
                    "Compare MSFT against AAPL, but focus mainly on AAPL "
                    "going forward."
                ),
            }
        ],
    )

    assert context.confirmed_symbol == "AAPL"
    assert context.symbol_candidates[:2] == ("AAPL", "MSFT")


def test_common_acronym_is_not_a_historical_symbol():
    context = DeepResearchContext.from_history(
        current_request="Continue that analysis.",
        conversation_history=[
            {"role": "user", "content": "Analyze AAPL using AI."},
        ],
    )

    assert context.confirmed_symbol == "AAPL"
    assert context.symbol_candidates == ("AAPL",)


def test_latest_assistant_symbol_precedes_older_user_symbol():
    context = DeepResearchContext.from_history(
        current_request="Continue that analysis.",
        conversation_history=[
            {"role": "user", "content": "Analyze AAPL first."},
            {"role": "user", "content": "Now analyze Microsoft instead."},
            {"role": "assistant", "content": "The MSFT verdict is HOLD."},
        ],
    )

    assert context.confirmed_symbol == "MSFT"
    assert context.symbol_candidates == ("MSFT",)


def test_render_can_limit_previous_report_excerpt():
    context = DeepResearchContext.from_history(
        current_request="Challenge the prior thesis.",
        conversation_history=[
            {"role": "assistant", "content": "A" * 900 + "LATEST_RISK_MARKER"}
        ],
    )

    compact = context.render(symbol="AAPL", previous_report_char_limit=600)
    full = context.render(symbol="AAPL")

    assert "LATEST_RISK_MARKER" not in compact
    assert "LATEST_RISK_MARKER" in full
    assert len(compact) < len(full)


def test_current_intent_overrides_conflicting_history():
    context = DeepResearchContext.from_history(
        current_request="改成12个月周期，只看技术面，风险偏好改为激进。",
        conversation_history=[
            {
                "role": "user",
                "content": (
                    "Analyze AAPL over 6 months with moderate risk and "
                    "focus on valuation."
                ),
            }
        ],
    )

    assert context.investment_horizon == "12个月"
    assert context.risk_tolerance == "aggressive"
    assert context.constraints == ("technical_focus",)


def test_latest_historical_focus_replaces_older_focus():
    context = DeepResearchContext.from_history(
        current_request="Use the same constraints and continue.",
        conversation_history=[
            {"role": "user", "content": "Analyze AAPL using technical only."},
            {"role": "assistant", "content": "AAPL technical report."},
            {"role": "user", "content": "Switch to valuation only."},
            {"role": "assistant", "content": "AAPL valuation report."},
        ],
    )

    assert context.constraints == ("valuation_focus",)


def test_render_budget_includes_current_request():
    context = DeepResearchContext.from_history(
        current_request="Analyze AAPL. " + ("X" * 10_000),
        conversation_history=[],
    )

    assert context.truncated is True
    assert len(context.render(symbol="AAPL")) <= 6000
    assert len(context.current_request) <= 2000


def test_new_symbol_drops_old_thesis_and_unrequested_settings():
    context = DeepResearchContext.from_history(
        current_request="Analyze MSFT.",
        conversation_history=[
            {
                "role": "user",
                "content": (
                    "Analyze AAPL over 6 months with moderate risk and "
                    "valuation only."
                ),
            },
            {"role": "assistant", "content": "The AAPL thesis is bullish."},
        ],
    )

    retargeted = context.for_new_symbol()

    assert retargeted.previous_user_request is None
    assert retargeted.previous_assistant_report is None
    assert retargeted.investment_horizon is None
    assert retargeted.risk_tolerance is None
    assert retargeted.constraints == ()
    assert retargeted.relevant_turns == ()


def test_new_symbol_can_reuse_explicitly_requested_settings():
    context = DeepResearchContext.from_history(
        current_request="Use the same constraints and analyze MSFT.",
        conversation_history=[
            {
                "role": "user",
                "content": (
                    "Analyze AAPL over 6 months with moderate risk and "
                    "valuation only."
                ),
            },
            {"role": "assistant", "content": "The AAPL thesis is bullish."},
        ],
    )

    retargeted = context.for_new_symbol()

    assert retargeted.previous_assistant_report is None
    assert retargeted.investment_horizon == "6 months"
    assert retargeted.risk_tolerance == "moderate"
    assert retargeted.constraints == ("valuation_focus",)


def test_latest_symbol_segment_excludes_old_symbol_settings():
    context = DeepResearchContext.from_history(
        current_request="Continue that thesis.",
        conversation_history=[
            {
                "role": "user",
                "content": (
                    "Analyze AAPL over 6 months with conservative risk and "
                    "valuation only."
                ),
            },
            {"role": "assistant", "content": "The AAPL thesis is bullish."},
            {"role": "user", "content": "Analyze Microsoft instead."},
            {"role": "assistant", "content": "The MSFT thesis is neutral."},
        ],
    )

    assert context.confirmed_symbol == "MSFT"
    assert context.previous_user_request == "Analyze Microsoft instead."
    assert context.previous_assistant_report == "The MSFT thesis is neutral."
    assert context.investment_horizon is None
    assert context.risk_tolerance is None
    assert context.constraints == ()
    assert all("AAPL" not in turn.content for turn in context.relevant_turns)


def test_unrelated_request_does_not_allow_symbol_reuse():
    context = DeepResearchContext.from_history(
        current_request="Analyze a company.",
        conversation_history=[
            {"role": "assistant", "content": "Prior report about TSLA."},
        ],
    )

    assert context.confirmed_symbol == "TSLA"
    assert context.allows_symbol_reuse is False


def test_review_intensity_does_not_override_investor_risk_tolerance():
    context = DeepResearchContext.from_history(
        current_request="Challenge the thesis more aggressively.",
        conversation_history=[
            {
                "role": "user",
                "content": "Analyze SKHY with moderate risk tolerance.",
            }
        ],
    )

    assert context.risk_tolerance == "moderate"
    assert "adversarial_review" in context.constraints
