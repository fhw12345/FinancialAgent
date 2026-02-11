"""
Deep Agent event schema for SSE streaming.

Defines structured lifecycle events emitted during deep agent analysis.
Events follow a hierarchical pattern: deep_start -> subagent_start -> tool_start/end
-> subagent_result -> debate_start/round -> synthesis_start -> verdict.

Each event includes a monotonically increasing `seq` field for frontend ordering.
"""

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

import structlog

logger = structlog.get_logger()

# ===== Event Type Definitions (documentation only, factory returns dict) =====
# Each event shares base fields: type (str), seq (int), timestamp (str ISO 8601)


class DeepStartEvent(TypedDict):
    """Emitted when deep analysis begins."""

    type: Literal["deep_start"]
    seq: int
    timestamp: str
    symbol: str
    subagent_names: list[str]
    enable_debate: bool


class DeepSubagentStartEvent(TypedDict):
    """Emitted when a sub-agent begins execution."""

    type: Literal["deep_subagent_start"]
    seq: int
    timestamp: str
    subagent_name: str
    display_name: str
    icon: str
    tool_names: list[str]


class DeepToolStartEvent(TypedDict):
    """Emitted when a tool begins execution within a sub-agent."""

    type: Literal["deep_tool_start"]
    seq: int
    timestamp: str
    subagent_name: str
    tool_name: str
    display_name: str
    inputs: dict[str, Any]


class DeepToolEndEvent(TypedDict):
    """Emitted when a tool completes execution."""

    type: Literal["deep_tool_end"]
    seq: int
    timestamp: str
    subagent_name: str
    tool_name: str
    status: Literal["success", "error"]
    duration_ms: int
    output_preview: str  # First 200 chars


class DeepSubagentResultEvent(TypedDict):
    """Emitted when a sub-agent completes its analysis."""

    type: Literal["deep_subagent_result"]
    seq: int
    timestamp: str
    subagent_name: str
    status: Literal["success", "error"]
    duration_ms: int
    result_summary: str  # Full text (frontend handles truncation/expand)
    tool_count: int


class DeepDebateStartEvent(TypedDict):
    """Emitted when the debate verification phase begins."""

    type: Literal["deep_debate_start"]
    seq: int
    timestamp: str
    round: int
    max_rounds: int


class DeepDebateRoundEvent(TypedDict):
    """Emitted after each debate round completes."""

    type: Literal["deep_debate_round"]
    seq: int
    timestamp: str
    round: int
    has_concerns: bool
    summary: str  # Full text (frontend handles truncation/expand)


class DeepRebuttalStartEvent(TypedDict):
    """Emitted when the rebuttal/defense phase begins."""

    type: Literal["deep_rebuttal_start"]
    seq: int
    timestamp: str
    round: int


class DeepRebuttalResultEvent(TypedDict):
    """Emitted when the rebuttal/defense phase completes."""

    type: Literal["deep_rebuttal_result"]
    seq: int
    timestamp: str
    round: int
    defense_summary: str
    tool_count: int
    duration_ms: int


class DeepSynthesisStartEvent(TypedDict):
    """Emitted when the final synthesis/report generation begins."""

    type: Literal["deep_synthesis_start"]
    seq: int
    timestamp: str


class DeepVerdictEvent(TypedDict):
    """Emitted with the final analysis verdict."""

    type: Literal["deep_verdict"]
    seq: int
    timestamp: str
    verdict_text: str
    risk_level: str | None  # "HIGH", "MODERATE", "LOW", etc.
    tool_count: int
    total_duration_ms: int


# ===== All Event Types (Union) =====

DeepAgentEvent = (
    DeepStartEvent
    | DeepSubagentStartEvent
    | DeepToolStartEvent
    | DeepToolEndEvent
    | DeepSubagentResultEvent
    | DeepDebateStartEvent
    | DeepDebateRoundEvent
    | DeepRebuttalStartEvent
    | DeepRebuttalResultEvent
    | DeepSynthesisStartEvent
    | DeepVerdictEvent
)

# All valid event type strings
DEEP_EVENT_TYPES = frozenset(
    {
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
)


# ===== Sub-Agent Display Metadata =====

SUBAGENT_DISPLAY: dict[str, dict[str, str]] = {
    "technical_analyst": {"display_name": "Technical Analyst", "icon": "📊"},
    "news_analyst": {"display_name": "News Analyst", "icon": "📰"},
    "financial_analyst": {"display_name": "Financial Analyst", "icon": "💰"},
    "debater": {"display_name": "Debate Verification", "icon": "⚖️"},
}

# Tool display name mapping
TOOL_DISPLAY_NAMES: dict[str, str] = {
    "fibonacci_analysis_tool": "Fibonacci Analysis",
    "stochastic_analysis_tool": "Stochastic Analysis",
    "get_historical_prices": "Historical Prices",
    "get_news_sentiment": "News Sentiment",
    "get_market_movers": "Market Movers",
    "get_company_overview": "Company Overview",
    "get_financial_statements": "Financial Statements",
    "get_company_earnings": "Earnings Data",
    "get_insider_activity": "Insider Activity",
    "get_etf_holdings": "ETF Holdings",
    "search_ticker": "Symbol Search",
    "list_insight_categories": "Insight Categories",
    "get_insight_category": "Insight Category",
    "get_insight_metric": "Insight Metric",
    "get_insight_trend": "Insight Trend",
    "get_put_call_ratio": "Put/Call Ratio",
    "get_copper_commodity": "Commodity Prices",
    "read_file": "Read Skill File",
}


# ===== Event Factory =====


class DeepEventEmitter:
    """Factory for creating sequenced deep agent events.

    Maintains a monotonically increasing sequence counter per stream.

    NOT thread-safe. Relies on sequential sub-agent invocation within
    a single asyncio event loop. Do NOT use with asyncio.gather() or
    concurrent coroutines without adding synchronization.
    """

    def __init__(self) -> None:
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _base(self, event_type: str) -> dict[str, Any]:
        return {
            "type": event_type,
            "seq": self._next_seq(),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def deep_start(
        self,
        symbol: str,
        subagent_names: list[str],
        enable_debate: bool,
    ) -> dict[str, Any]:
        """Create a deep_start event."""
        return {
            **self._base("deep_start"),
            "symbol": symbol,
            "subagent_names": subagent_names,
            "enable_debate": enable_debate,
        }

    def subagent_start(
        self,
        subagent_name: str,
        tool_names: list[str],
    ) -> dict[str, Any]:
        """Create a deep_subagent_start event."""
        display = SUBAGENT_DISPLAY.get(
            subagent_name,
            {"display_name": subagent_name.replace("_", " ").title(), "icon": "🤖"},
        )
        return {
            **self._base("deep_subagent_start"),
            "subagent_name": subagent_name,
            "display_name": display["display_name"],
            "icon": display["icon"],
            "tool_names": tool_names,
        }

    def tool_start(
        self,
        subagent_name: str,
        tool_name: str,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a deep_tool_start event."""
        display_name = TOOL_DISPLAY_NAMES.get(
            tool_name, tool_name.replace("_", " ").title()
        )
        return {
            **self._base("deep_tool_start"),
            "subagent_name": subagent_name,
            "tool_name": tool_name,
            "display_name": display_name,
            "inputs": inputs or {},
        }

    def tool_end(
        self,
        subagent_name: str,
        tool_name: str,
        status: Literal["success", "error"],
        duration_ms: int,
        output_preview: str = "",
    ) -> dict[str, Any]:
        """Create a deep_tool_end event."""
        return {
            **self._base("deep_tool_end"),
            "subagent_name": subagent_name,
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "output_preview": output_preview[:200],
        }

    def subagent_result(
        self,
        subagent_name: str,
        status: Literal["success", "error"],
        duration_ms: int,
        result_summary: str = "",
        tool_count: int = 0,
    ) -> dict[str, Any]:
        """Create a deep_subagent_result event."""
        return {
            **self._base("deep_subagent_result"),
            "subagent_name": subagent_name,
            "status": status,
            "duration_ms": duration_ms,
            "result_summary": result_summary,
            "tool_count": tool_count,
        }

    def debate_start(
        self,
        current_round: int,
        max_rounds: int,
    ) -> dict[str, Any]:
        """Create a deep_debate_start event."""
        return {
            **self._base("deep_debate_start"),
            "round": current_round,
            "max_rounds": max_rounds,
        }

    def debate_round(
        self,
        current_round: int,
        has_concerns: bool,
        summary: str = "",
    ) -> dict[str, Any]:
        """Create a deep_debate_round event."""
        return {
            **self._base("deep_debate_round"),
            "round": current_round,
            "has_concerns": has_concerns,
            "summary": summary,
        }

    def rebuttal_start(self, current_round: int) -> dict[str, Any]:
        """Create a deep_rebuttal_start event."""
        return {
            **self._base("deep_rebuttal_start"),
            "round": current_round,
        }

    def rebuttal_result(
        self,
        current_round: int,
        defense_summary: str,
        tool_count: int,
        duration_ms: int,
    ) -> dict[str, Any]:
        """Create a deep_rebuttal_result event."""
        return {
            **self._base("deep_rebuttal_result"),
            "round": current_round,
            "defense_summary": defense_summary,
            "tool_count": tool_count,
            "duration_ms": duration_ms,
        }

    def synthesis_start(self) -> dict[str, Any]:
        """Create a deep_synthesis_start event."""
        return self._base("deep_synthesis_start")

    def verdict(
        self,
        verdict_text: str,
        risk_level: str | None,
        tool_count: int,
        total_duration_ms: int,
    ) -> dict[str, Any]:
        """Create a deep_verdict event."""
        return {
            **self._base("deep_verdict"),
            "verdict_text": verdict_text,
            "risk_level": risk_level,
            "tool_count": tool_count,
            "total_duration_ms": total_duration_ms,
        }


# ===== Helper: Extract risk level from report text =====


def extract_risk_level(report: str) -> str | None:
    """Extract risk level from analysis report text.

    Searches for patterns like "Risk Level: HIGH" or keywords like "high risk".
    Returns the risk level string or None if not found.
    """
    report_upper = report.upper()
    for level in ("HIGH", "MODERATE", "LOW", "EXTREME"):
        if f"RISK LEVEL: {level}" in report_upper:
            return level
        if f"RISK: {level}" in report_upper:
            return level
    if "HIGH RISK" in report_upper or "HIGH-RISK" in report_upper:
        return "HIGH"
    if "MODERATE RISK" in report_upper or "MEDIUM RISK" in report_upper:
        return "MODERATE"
    if "LOW RISK" in report_upper or "LOW-RISK" in report_upper:
        return "LOW"
    return None
