"""
Runtime Context for Agent Invocations.

This module provides a unified context object for agent sessions,
enabling dependency injection for tools, skills, and middleware.

Key Features:
- Session tracking (user_id, session_id)
- Analysis parameters (symbol, timeframe, risk tolerance)
- Time context (current_date, lookback periods)
- Serialization for state passing across LangGraph nodes

Usage:
    context = AgentContext(symbol="AAPL", user_id="user123")
    # Pass to agent invocation
    response = agent.invoke({"messages": [...], "context": context})
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

# All "today/now" defaults shown to the LLM and to the user use Beijing time.
# The user is in CN; UTC midnight rollover would otherwise show "yesterday"
# for half the day.
_LOCAL_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class AgentContext:
    """
    Runtime context for agent invocations.

    This provides dependency injection for tools and middleware,
    making agents more testable, reusable, and flexible.
    """

    # Session info
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_id: str = "anonymous"

    # Analysis target
    symbol: str = "AAPL"
    analysis_type: str = "investment"  # investment, technical, fundamental

    # Time context (critical for relative date queries)
    current_date: str = field(
        default_factory=lambda: datetime.now(_LOCAL_TZ).strftime("%Y-%m-%d")
    )
    six_months_ago: str = field(
        default_factory=lambda: (
            datetime.now(_LOCAL_TZ) - timedelta(days=180)
        ).strftime("%Y-%m-%d")
    )

    # Configuration
    max_debate_rounds: int = 3
    risk_tolerance: str = "moderate"  # conservative, moderate, aggressive
    enable_debate: bool = True  # Enable adversarial verification

    def __post_init__(self) -> None:
        """Generate derived fields after initialization."""
        # Ensure dates are strings
        if isinstance(self.current_date, datetime):
            self.current_date = self.current_date.strftime("%Y-%m-%d")
        if isinstance(self.six_months_ago, datetime):
            self.six_months_ago = self.six_months_ago.strftime("%Y-%m-%d")

    def to_dict(self) -> dict[str, Any]:
        """Serialize context for state passing."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "symbol": self.symbol,
            "analysis_type": self.analysis_type,
            "current_date": self.current_date,
            "six_months_ago": self.six_months_ago,
            "max_debate_rounds": self.max_debate_rounds,
            "risk_tolerance": self.risk_tolerance,
            "enable_debate": self.enable_debate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentContext":
        """Deserialize context from state."""
        return cls(
            session_id=data.get("session_id", str(uuid.uuid4())[:8]),
            user_id=data.get("user_id", "anonymous"),
            symbol=data.get("symbol", "AAPL"),
            analysis_type=data.get("analysis_type", "investment"),
            current_date=data.get(
                "current_date", datetime.now(_LOCAL_TZ).strftime("%Y-%m-%d")
            ),
            six_months_ago=data.get(
                "six_months_ago",
                (datetime.now(_LOCAL_TZ) - timedelta(days=180)).strftime("%Y-%m-%d"),
            ),
            max_debate_rounds=data.get("max_debate_rounds", 3),
            risk_tolerance=data.get("risk_tolerance", "moderate"),
            enable_debate=data.get("enable_debate", True),
        )

    def to_context_header(self) -> str:
        """Generate context header for system prompts."""
        return f"""=== SESSION CONTEXT ===
Session ID: {self.session_id}
User ID: {self.user_id}
Symbol: {self.symbol}
Analysis Type: {self.analysis_type}
Current Date: {self.current_date}
Analysis Period: {self.six_months_ago} to {self.current_date}
Risk Tolerance: {self.risk_tolerance}
========================"""
