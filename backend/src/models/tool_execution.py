"""
Tool execution tracking for 1st-party and 3rd-party tools.

Enables:
1. State restoration: Replay tool calls in sorted order
2. Cost tracking: Track paid API calls (Alpha Vantage, etc.)
3. Audit trail: See what data informed each decision
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ToolExecution(BaseModel):
    """
    Generic tool execution record for 1st-party and 3rd-party tools.

    Records every tool call made by the agent, including:
    - Local tools (fibonacci_analysis_tool, stochastic_analysis_tool)
    - MCP tools (GLOBAL_QUOTE, RSI, NEWS_SENTIMENT, etc.)

    Enables cost tracking and state restoration.
    """

    # Our database ID
    execution_id: str = Field(..., description="UUID for this execution")

    # Foreign keys (linking to analysis workflow)
    chat_id: str = Field(..., description="Chat where tool was executed")
    analysis_id: str = Field(
        ..., description="Analysis workflow this execution belongs to"
    )
    message_id: str | None = Field(None, description="Message that triggered tool call")

    # Tool identification (CRITICAL - differentiates 1st vs 3rd party)
    tool_name: str = Field(
        ..., description="Tool name (e.g., fibonacci_analysis_tool, GLOBAL_QUOTE)"
    )
    tool_source: str = Field(
        ...,
        description="1st_party | mcp_alphavantage | future_mcp_server",
    )

    # Execution details
    input_params: dict = Field(..., description="Tool input parameters")
    output_result: str | dict | list = Field(..., description="Tool output")

    # Status
    status: str = Field(..., description="success | error | timeout")
    error_message: str | None = Field(None, description="Error details if failed")

    # Timing
    started_at: datetime = Field(..., description="Execution start time")
    completed_at: datetime | None = Field(None, description="Execution end time")
    duration_ms: int | None = Field(
        None, description="Execution duration in milliseconds"
    )

    # Cost tracking (for paid APIs)
    is_paid_api: bool = Field(False, description="Whether this tool costs money")
    api_cost: float | None = Field(None, description="Cost in USD (if paid API)")

    # Cache tracking
    cache_hit: bool = Field(False, description="Whether result came from Redis cache")
    cache_key: str | None = Field(None, description="Redis cache key used")

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "exec_abc123",
                "chat_id": "chat_xyz789",
                "analysis_id": "analysis-20251101-AAPL-bullish",
                "message_id": "msg_456",
                "tool_name": "GLOBAL_QUOTE",
                "tool_source": "mcp_alphavantage",
                "input_params": {"symbol": "AAPL"},
                "output_result": {
                    "symbol": "AAPL",
                    "price": "271.55",
                    "volume": "67844982",
                },
                "status": "success",
                "started_at": "2025-11-01T14:30:00.123Z",
                "completed_at": "2025-11-01T14:30:01.456Z",
                "duration_ms": 1333,
                "is_paid_api": True,
                "api_cost": 0.00004,
                "cache_hit": False,
                "cache_key": None,
            }
        }


class ToolExecutionInDB(ToolExecution):
    """Tool execution with database ID."""

    id: str = Field(alias="_id")


class ToolExecutionSummary(BaseModel):
    """Summary of tool executions for cost tracking."""

    tool_source: str = Field(
        ..., description="Tool source (1st_party, mcp_alphavantage)"
    )
    tool_name: str = Field(..., description="Tool name")

    # Call statistics
    total_calls: int = Field(..., description="Total number of calls")
    successful_calls: int = Field(..., description="Successful calls")
    failed_calls: int = Field(..., description="Failed calls")

    # Cache statistics
    cache_hits: int = Field(..., description="Number of cache hits")
    cache_misses: int = Field(..., description="Number of cache misses")
    cache_hit_rate: float = Field(..., description="Cache hit rate (0-1)")

    # Cost statistics
    total_cost: float = Field(..., description="Total API cost in USD")
    avg_duration_ms: float = Field(..., description="Average execution duration")

    # Time range
    start_date: datetime = Field(..., description="Start of summary period")
    end_date: datetime = Field(..., description="End of summary period")

    class Config:
        json_schema_extra = {
            "example": {
                "tool_source": "mcp_alphavantage",
                "tool_name": "GLOBAL_QUOTE",
                "total_calls": 100,
                "successful_calls": 98,
                "failed_calls": 2,
                "cache_hits": 80,
                "cache_misses": 20,
                "cache_hit_rate": 0.80,
                "total_cost": 0.0008,
                "avg_duration_ms": 1200,
                "start_date": "2025-11-01T00:00:00Z",
                "end_date": "2025-11-01T23:59:59Z",
            }
        }
