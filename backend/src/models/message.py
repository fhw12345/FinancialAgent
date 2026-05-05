"""
Message models for chat conversations.
Everything is a message - user text, LLM responses, and analysis results.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..api.models import ToolCall


class MessageMetadata(BaseModel):
    """
    Flexible metadata for messages.
    Contains analysis data for Fibonacci, Stochastic, etc.
    """

    # Common fields for analysis messages
    symbol: str | None = Field(default=None, description="Stock symbol")
    timeframe: str | None = Field(default=None, description="Analysis timeframe")

    # Fibonacci-specific
    fibonacci_levels: list[dict[str, Any]] | None = Field(
        default=None, description="Fibonacci retracement levels"
    )
    trend_direction: str | None = Field(
        default=None, description="uptrend or downtrend"
    )
    swing_high: dict[str, Any] | None = Field(
        default=None, description="Swing high price and date"
    )
    swing_low: dict[str, Any] | None = Field(
        default=None, description="Swing low price and date"
    )
    confidence_score: float | None = Field(
        default=None, description="Analysis confidence"
    )

    # Stochastic-specific
    stochastic_k: float | None = Field(default=None, description="%K value")
    stochastic_d: float | None = Field(default=None, description="%D value")
    overbought: bool | None = Field(default=None, description="Overbought condition")
    oversold: bool | None = Field(default=None, description="Oversold condition")

    # LLM-specific
    model: str | None = Field(default=None, description="LLM model used")
    tokens: int | None = Field(default=None, description="Total token count")
    input_tokens: int | None = Field(default=None, description="Input tokens consumed")
    output_tokens: int | None = Field(
        default=None, description="Output tokens generated"
    )

    # Credit transaction linkage
    transaction_id: str | None = Field(
        default=None, description="Links to credit transaction for this message"
    )

    # LangGraph agent tracing
    trace_id: str | None = Field(
        default=None, description="OpenTelemetry trace ID for observability"
    )
    selected_tool: str | None = Field(
        default=None,
        description="Tool selected by LangGraph agent (fibonacci/stochastic)",
    )
    has_tool_result: bool | None = Field(
        default=None, description="Whether agent executed a tool in this response"
    )

    # Portfolio tracking (for order placement and analysis workflow)
    analysis_id: str | None = Field(
        default=None, description="Analysis workflow ID this message belongs to"
    )
    analysis_type: str | None = Field(
        default=None,
        description="Type of analysis: 'individual' (Phase 1 symbol research) or 'portfolio' (Phase 2/3 portfolio decisions)",
    )
    order_placed: bool | None = Field(
        default=None, description="Whether this message placed an order"
    )
    order_id: str | None = Field(
        default=None, description="FK to portfolio_orders.order_id"
    )
    tool_execution_ids: list[str] | None = Field(
        default=None,
        description="List of tool_executions.execution_id for this message",
    )
    tool_summary: dict[str, Any] | None = Field(
        default=None,
        description="Summary: {tool_name: {cache_hit, duration_ms, cost}}",
    )

    # Context compaction
    is_summary: bool = Field(
        default=False,
        description="True if this message is a compacted summary of older messages",
    )
    summarized_message_count: int | None = Field(
        default=None,
        description="Number of messages that were summarized into this message",
    )

    # Extensible - any additional data
    raw_data: dict[str, Any] | None = Field(
        default=None, description="Raw analysis data"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "timeframe": "1d",
                "fibonacci_levels": [
                    {"level": 0, "price": 150.0, "percentage": "0%"},
                    {"level": 0.618, "price": 186.18, "percentage": "61.8%"},
                ],
                "trend_direction": "uptrend",
                "swing_high": {"price": 210.0, "date": "2025-10-01"},
                "swing_low": {"price": 150.0, "date": "2025-09-01"},
                "confidence_score": 0.85,
            }
        }


class MessageCreate(BaseModel):
    """Request model for creating a new message."""

    chat_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    source: Literal["user", "llm", "tool"]
    metadata: MessageMetadata = MessageMetadata()
    tool_call: ToolCall | None = None


class Message(BaseModel):
    """
    Message model for database storage.
    Represents user messages, LLM responses, and analysis results.
    """

    message_id: str = Field(..., description="Unique message identifier")
    chat_id: str = Field(..., description="Chat this message belongs to")

    role: Literal["user", "assistant", "system"] = Field(
        ..., description="Message role"
    )
    content: str = Field(..., description="Message text content")
    content_zh: str | None = Field(
        default=None,
        description="Simplified Chinese translation of content; None when translation failed or not yet computed",
    )
    source: Literal["user", "llm", "tool"] = Field(
        ...,
        description="Message source: 'user' (user input), 'llm' (LLM response), 'tool' (tool output). Use metadata.selected_tool to identify specific tool.",
    )

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: MessageMetadata = Field(
        default=MessageMetadata(),
        description="Flexible metadata for analysis data",
    )

    # Tool invocation metadata for UI rendering
    tool_call: ToolCall | None = Field(
        default=None,
        description="Tool invocation metadata for collapsible UI wrapper (when source='tool')",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "msg_abc123",
                "chat_id": "chat_xyz789",
                "role": "assistant",
                "content": "## Fibonacci Analysis - AAPL\n\nLevels calculated...",
                "source": "fibonacci",
                "timestamp": "2025-10-05T10:15:00Z",
                "metadata": {
                    "symbol": "AAPL",
                    "timeframe": "1d",
                    "fibonacci_levels": [
                        {"level": 0.618, "price": 186.18, "percentage": "61.8%"}
                    ],
                },
            }
        }


class MessageInDB(Message):
    """Message model with database ID."""

    id: str = Field(alias="_id")
