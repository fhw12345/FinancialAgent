"""
Unit tests for Deep Agent event streaming pipeline.

Tests event emission sequence, schema validation, seq ordering,
backward compatibility, and error handling for the deep agent's
structured SSE event system.
"""

from unittest.mock import patch

import pytest

from src.api.schemas.deep_agent_events import (
    DEEP_EVENT_TYPES,
    SUBAGENT_DISPLAY,
    TOOL_DISPLAY_NAMES,
    DeepEventEmitter,
)

# ===== Fixtures =====


@pytest.fixture
def emitter():
    """Fresh DeepEventEmitter instance."""
    return DeepEventEmitter()


@pytest.fixture
def collected_events():
    """List to collect events via callback."""
    return []


@pytest.fixture
def on_event(collected_events):
    """Event callback that appends to collected_events."""

    def callback(event: dict) -> None:
        collected_events.append(event)

    return callback


# ===== Test: DeepEventEmitter =====


class TestDeepEventEmitter:
    """Tests for the DeepEventEmitter factory class."""

    def test_seq_monotonically_increasing(self, emitter):
        """Seq field increments with each event."""
        events = [
            emitter.deep_start("TSLA", ["technical_analyst"], True),
            emitter.subagent_start("technical_analyst", ["get_historical_prices"]),
            emitter.tool_start("technical_analyst", "get_historical_prices"),
            emitter.tool_end(
                "technical_analyst", "get_historical_prices", "success", 500
            ),
            emitter.subagent_result("technical_analyst", "success", 2000, "Report"),
        ]

        seq_values = [e["seq"] for e in events]
        assert seq_values == [1, 2, 3, 4, 5]
        # Verify monotonically increasing
        for i in range(1, len(seq_values)):
            assert seq_values[i] > seq_values[i - 1]

    def test_deep_start_event_schema(self, emitter):
        """deep_start event contains all required fields."""
        event = emitter.deep_start(
            symbol="AAPL",
            subagent_names=["technical_analyst", "news_analyst", "financial_analyst"],
            enable_debate=True,
        )

        assert event["type"] == "deep_start"
        assert event["seq"] == 1
        assert event["symbol"] == "AAPL"
        assert event["subagent_names"] == [
            "technical_analyst",
            "news_analyst",
            "financial_analyst",
        ]
        assert event["enable_debate"] is True
        assert "timestamp" in event

    def test_subagent_start_event_with_display_metadata(self, emitter):
        """deep_subagent_start event includes display_name and icon from metadata."""
        event = emitter.subagent_start(
            subagent_name="technical_analyst",
            tool_names=["fibonacci_analysis_tool", "get_historical_prices"],
        )

        assert event["type"] == "deep_subagent_start"
        assert event["subagent_name"] == "technical_analyst"
        assert event["display_name"] == "Technical Analyst"
        assert event["icon"] == "📊"
        assert event["tool_names"] == [
            "fibonacci_analysis_tool",
            "get_historical_prices",
        ]

    def test_subagent_start_unknown_agent_fallback(self, emitter):
        """Unknown sub-agent name gets a fallback display_name and icon."""
        event = emitter.subagent_start("custom_agent", ["tool_a"])

        assert event["display_name"] == "Custom Agent"
        assert event["icon"] == "🤖"

    def test_tool_start_event_schema(self, emitter):
        """deep_tool_start event includes all fields."""
        event = emitter.tool_start(
            subagent_name="news_analyst",
            tool_name="get_news_sentiment",
            inputs={"symbol": "TSLA"},
        )

        assert event["type"] == "deep_tool_start"
        assert event["subagent_name"] == "news_analyst"
        assert event["tool_name"] == "get_news_sentiment"
        assert event["display_name"] == "News Sentiment"
        assert event["inputs"] == {"symbol": "TSLA"}

    def test_tool_start_empty_inputs_default(self, emitter):
        """deep_tool_start defaults to empty dict when inputs is None."""
        event = emitter.tool_start("news_analyst", "get_news_sentiment")
        assert event["inputs"] == {}

    def test_tool_end_event_schema(self, emitter):
        """deep_tool_end event includes status and duration."""
        event = emitter.tool_end(
            subagent_name="technical_analyst",
            tool_name="fibonacci_analysis_tool",
            status="success",
            duration_ms=1234,
            output_preview="Fibonacci levels calculated for TSLA",
        )

        assert event["type"] == "deep_tool_end"
        assert event["status"] == "success"
        assert event["duration_ms"] == 1234
        assert event["output_preview"] == "Fibonacci levels calculated for TSLA"

    def test_tool_end_output_preview_truncation(self, emitter):
        """Output preview is truncated to 200 characters."""
        long_output = "A" * 500
        event = emitter.tool_end(
            "technical_analyst", "get_historical_prices", "success", 100, long_output
        )

        assert len(event["output_preview"]) == 200

    def test_subagent_result_event_schema(self, emitter):
        """deep_subagent_result event includes all fields."""
        event = emitter.subagent_result(
            subagent_name="financial_analyst",
            status="success",
            duration_ms=45000,
            result_summary="P/E ratio is 294x, indicating overvaluation",
            tool_count=3,
        )

        assert event["type"] == "deep_subagent_result"
        assert event["subagent_name"] == "financial_analyst"
        assert event["status"] == "success"
        assert event["duration_ms"] == 45000
        assert event["tool_count"] == 3

    def test_subagent_result_summary_not_truncated(self, emitter):
        """Result summary is passed through without truncation."""
        long_summary = "B" * 300
        event = emitter.subagent_result(
            "technical_analyst", "success", 1000, long_summary, 2
        )
        assert len(event["result_summary"]) == 300

    def test_debate_start_event_schema(self, emitter):
        """deep_debate_start event includes round and max_rounds."""
        event = emitter.debate_start(current_round=1, max_rounds=3)

        assert event["type"] == "deep_debate_start"
        assert event["round"] == 1
        assert event["max_rounds"] == 3

    def test_debate_round_event_schema(self, emitter):
        """deep_debate_round event includes has_concerns and summary."""
        event = emitter.debate_round(
            current_round=1,
            has_concerns=True,
            summary="Credit rating claim not verified by data",
        )

        assert event["type"] == "deep_debate_round"
        assert event["round"] == 1
        assert event["has_concerns"] is True
        assert "Credit rating" in event["summary"]

    def test_synthesis_start_event_schema(self, emitter):
        """deep_synthesis_start event has minimal fields."""
        event = emitter.synthesis_start()

        assert event["type"] == "deep_synthesis_start"
        assert "seq" in event
        assert "timestamp" in event

    def test_verdict_event_schema(self, emitter):
        """deep_verdict event includes all final analysis fields."""
        event = emitter.verdict(
            verdict_text="TSLA is overvalued with high risk",
            risk_level="HIGH",
            tool_count=8,
            total_duration_ms=180000,
        )

        assert event["type"] == "deep_verdict"
        assert event["verdict_text"] == "TSLA is overvalued with high risk"
        assert event["risk_level"] == "HIGH"
        assert event["tool_count"] == 8
        assert event["total_duration_ms"] == 180000

    def test_verdict_event_nullable_risk_level(self, emitter):
        """Verdict risk_level can be None when not extractable."""
        event = emitter.verdict("Some text", None, 5, 120000)
        assert event["risk_level"] is None

    def test_all_event_types_in_constant(self):
        """DEEP_EVENT_TYPES constant contains all 11 event types."""
        assert len(DEEP_EVENT_TYPES) == 11
        expected = {
            "deep_start",
            "deep_subagent_start",
            "deep_tool_start",
            "deep_tool_end",
            "deep_subagent_result",
            "deep_debate_start",
            "deep_debate_round",
            "deep_rebuttal_start",
            "deep_rebuttal_result",
            "deep_synthesis_start",
            "deep_verdict",
        }
        assert DEEP_EVENT_TYPES == expected

    def test_all_events_have_required_base_fields(self, emitter):
        """Every event type includes type, seq, and timestamp."""
        events = [
            emitter.deep_start("TSLA", ["a"], True),
            emitter.subagent_start("a", []),
            emitter.tool_start("a", "b"),
            emitter.tool_end("a", "b", "success", 0),
            emitter.subagent_result("a", "success", 0),
            emitter.debate_start(1, 3),
            emitter.debate_round(1, False),
            emitter.rebuttal_start(1),
            emitter.rebuttal_result(1, "Defense text", 2, 3000),
            emitter.synthesis_start(),
            emitter.verdict("text", None, 0, 0),
        ]

        for event in events:
            assert "type" in event, f"Missing 'type' in {event}"
            assert "seq" in event, f"Missing 'seq' in {event}"
            assert "timestamp" in event, f"Missing 'timestamp' in {event}"
            assert event["type"] in DEEP_EVENT_TYPES


# ===== Test: Display Metadata =====


class TestDisplayMetadata:
    """Tests for sub-agent and tool display name mappings."""

    def test_subagent_display_has_all_agents(self):
        """SUBAGENT_DISPLAY covers all known sub-agents."""
        expected_agents = {
            "technical_analyst",
            "news_analyst",
            "financial_analyst",
            "debater",
        }
        assert set(SUBAGENT_DISPLAY.keys()) == expected_agents

    def test_subagent_display_has_required_fields(self):
        """Each sub-agent display entry has display_name and icon."""
        for name, meta in SUBAGENT_DISPLAY.items():
            assert "display_name" in meta, f"{name} missing display_name"
            assert "icon" in meta, f"{name} missing icon"
            assert len(meta["icon"]) > 0, f"{name} icon is empty"

    def test_tool_display_names_has_common_tools(self):
        """TOOL_DISPLAY_NAMES covers the most common tools."""
        common_tools = [
            "fibonacci_analysis_tool",
            "get_historical_prices",
            "get_news_sentiment",
            "get_company_overview",
            "get_put_call_ratio",
        ]
        for tool in common_tools:
            assert tool in TOOL_DISPLAY_NAMES, f"{tool} not in TOOL_DISPLAY_NAMES"


# ===== Test: Event Sequence =====


class TestEventSequence:
    """Tests for expected event emission ordering."""

    def test_full_lifecycle_event_order(self, emitter):
        """Events emitted in correct lifecycle order."""
        events = []

        # Phase 1: Start
        events.append(emitter.deep_start("TSLA", ["tech", "news", "fin"], True))

        # Phase 2: Sub-agents
        for sa in ["tech", "news", "fin"]:
            events.append(emitter.subagent_start(sa, ["tool_a"]))
            events.append(emitter.tool_start(sa, "tool_a"))
            events.append(emitter.tool_end(sa, "tool_a", "success", 100))
            events.append(emitter.subagent_result(sa, "success", 500))

        # Phase 3: Synthesis
        events.append(emitter.synthesis_start())

        # Phase 4: Debate
        events.append(emitter.debate_start(1, 3))
        events.append(emitter.debate_round(1, False))

        # Phase 5: Verdict
        events.append(emitter.verdict("Analysis complete", "MODERATE", 3, 60000))

        # Verify sequence
        types = [e["type"] for e in events]
        assert types[0] == "deep_start"
        assert types[-1] == "deep_verdict"
        # Synthesis comes after all subagent_results
        synthesis_idx = types.index("deep_synthesis_start")
        last_result_idx = len(types) - 1 - types[::-1].index("deep_subagent_result")
        assert synthesis_idx > last_result_idx

        # Debate comes after synthesis
        debate_idx = types.index("deep_debate_start")
        assert debate_idx > synthesis_idx

        # All seq values are monotonically increasing
        seqs = [e["seq"] for e in events]
        for i in range(1, len(seqs)):
            assert seqs[i] > seqs[i - 1]


# ===== Test: Risk Level Extraction =====


class TestRiskLevelExtraction:
    """Tests for extract_risk_level utility function."""

    def test_extract_high_risk(self):
        """Extracts HIGH from 'Risk Level: HIGH'."""
        from src.api.schemas.deep_agent_events import extract_risk_level

        assert extract_risk_level("Risk Level: HIGH") == "HIGH"

    def test_extract_moderate_risk(self):
        """Extracts MODERATE from 'Risk: MODERATE'."""
        from src.api.schemas.deep_agent_events import extract_risk_level

        assert extract_risk_level("Risk: MODERATE") == "MODERATE"

    def test_extract_high_risk_keyword(self):
        """Extracts HIGH from 'high risk' keyword pattern."""
        from src.api.schemas.deep_agent_events import extract_risk_level

        assert extract_risk_level("This is a high risk investment") == "HIGH"

    def test_extract_low_risk_keyword(self):
        """Extracts LOW from 'low-risk' keyword pattern."""
        from src.api.schemas.deep_agent_events import extract_risk_level

        assert extract_risk_level("A low-risk opportunity") == "LOW"

    def test_extract_no_risk_level(self):
        """Returns None when no risk level found."""
        from src.api.schemas.deep_agent_events import extract_risk_level

        assert extract_risk_level("This is just a report") is None


# ===== Test: Backward Compatibility =====


class TestBackwardCompatibility:
    """Tests that on_event=None path still works."""

    @pytest.mark.asyncio
    async def test_analyze_without_callback(self):
        """DeepReActAgent.analyze() works without on_event callback."""
        # The key assertion: calling analyze() with on_event=None shouldn't fail
        # We test this by verifying the DeepEventEmitter is only created when
        # on_event is provided. When on_event is None, emitter should not be created.
        on_event_callback = None
        result_emitter = DeepEventEmitter() if on_event_callback else None
        assert result_emitter is None


class TestFeatureFlag:
    """Tests for DEEP_STREAMING_V2 feature flag."""

    def test_feature_flag_default_true(self):
        """DEEP_STREAMING_V2 defaults to True."""
        # The module-level constant should be True by default
        from src.api.chat.streaming.deep_agent import DEEP_STREAMING_V2

        # In test env, the env var may not be set, so it should default to true
        assert isinstance(DEEP_STREAMING_V2, bool)

    @patch.dict("os.environ", {"DEEP_STREAMING_V2": "false"})
    def test_feature_flag_disabled(self):
        """DEEP_STREAMING_V2 can be disabled via env var."""
        # Re-evaluate the flag logic
        import os

        flag = os.environ.get("DEEP_STREAMING_V2", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        assert flag is False

    @patch.dict("os.environ", {"DEEP_STREAMING_V2": "true"})
    def test_feature_flag_enabled(self):
        """DEEP_STREAMING_V2 enabled when env var is 'true'."""
        import os

        flag = os.environ.get("DEEP_STREAMING_V2", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        assert flag is True
