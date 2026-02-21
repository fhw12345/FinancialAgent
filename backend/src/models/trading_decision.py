"""
Trading Decision Models for Structured LLM Output.

These models enable reliable extraction of trading decisions from LLM responses
using `with_structured_output()` instead of regex parsing.

Architecture:
- TradingDecision: Phase 1 output per symbol (individual analysis)
- OptimizedOrder: Single order in the execution plan
- OrderExecutionPlan: Phase 2 aggregated output (after agent optimization)
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class TradingAction(StrEnum):
    """Trading action types."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    SWAP = "SWAP"


class TradingDecision(BaseModel):
    """
    Phase 1: Individual symbol trading decision from analysis.

    Extracted via `with_structured_output()` after ReAct agent completes
    tool-based analysis.

    Position Size Rules:
    - BUY: position_size_percent = % of buying_power to spend
    - SELL: position_size_percent = % of current holding to sell
    - SWAP: Sell position_size_percent of swap_from_symbol, buy equivalent value
    """

    symbol: str = Field(description="Stock ticker symbol being analyzed")
    decision: TradingAction = Field(
        description="Trading action: BUY, SELL, HOLD, or SWAP"
    )
    position_size_percent: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description=(
            "Position size as percentage. "
            "For BUY: % of buying_power to spend. "
            "For SELL: % of current holding quantity to sell. "
            "REQUIRED for BUY/SELL/SWAP, None only for HOLD."
        ),
    )
    swap_from_symbol: str | None = Field(
        default=None,
        description="If SWAP, which symbol to sell to fund the buy. None otherwise.",
    )
    confidence: int = Field(
        ge=1,
        le=10,
        description="Conviction level 1-10 (10 = highest confidence in decision)",
    )
    reasoning_summary: str = Field(
        max_length=500,
        description="Brief reasoning for the trading decision",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "AAPL",
                    "decision": "BUY",
                    "position_size_percent": 10,
                    "swap_from_symbol": None,
                    "confidence": 8,
                    "reasoning_summary": "Strong technical setup with Fibonacci support at $180. Bullish earnings momentum.",
                },
                {
                    "symbol": "TSLA",
                    "decision": "SELL",
                    "position_size_percent": 50,
                    "swap_from_symbol": None,
                    "confidence": 7,
                    "reasoning_summary": "Taking profits after 30% gain. RSI overbought, resistance at $280.",
                },
                {
                    "symbol": "NVDA",
                    "decision": "HOLD",
                    "position_size_percent": None,
                    "swap_from_symbol": None,
                    "confidence": 6,
                    "reasoning_summary": "Neutral signals. Wait for clearer trend direction.",
                },
            ]
        }
    }


class OptimizedOrder(BaseModel):
    """
    Single order in the execution plan after aggregation optimization.

    Created by the aggregation hook when the agent reviews all TradingDecisions
    and produces a final execution plan.
    """

    symbol: str = Field(description="Stock ticker symbol")
    side: Literal["buy", "sell"] = Field(description="Order side: buy or sell")
    shares: int = Field(ge=1, description="Number of shares to trade")
    estimated_price: float = Field(gt=0, description="Estimated price per share")
    estimated_cost: float = Field(description="Estimated total cost (shares * price)")
    original_size_percent: int = Field(
        description="Original position_size_percent from TradingDecision"
    )
    adjusted_size_percent: int | None = Field(
        default=None,
        description="Adjusted percentage after scaling (if scaling was applied)",
    )
    priority: int = Field(
        ge=1,
        description="Execution priority (1 = highest, SELLs get lower numbers)",
    )
    skip_reason: str | None = Field(
        default=None,
        description="If order should be skipped, reason why (e.g., 'insufficient_funds')",
    )
    is_cover: bool = Field(
        default=False,
        description="True if this is a BUY order to cover a short position",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "TSLA",
                    "side": "sell",
                    "shares": 10,
                    "estimated_price": 275.50,
                    "estimated_cost": 2755.00,
                    "original_size_percent": 50,
                    "adjusted_size_percent": None,
                    "priority": 1,
                    "skip_reason": None,
                },
                {
                    "symbol": "AAPL",
                    "side": "buy",
                    "shares": 5,
                    "estimated_price": 185.00,
                    "estimated_cost": 925.00,
                    "original_size_percent": 10,
                    "adjusted_size_percent": 7,
                    "priority": 2,
                    "skip_reason": None,
                },
            ]
        }
    }


class OrderExecutionPlan(BaseModel):
    """
    Phase 2: Complete execution plan from aggregation hook.

    The agent reviews all TradingDecisions, considers portfolio state,
    and produces an optimized execution plan with:
    - SELLs ordered first (to free up buying power)
    - BUYs scaled proportionally if buying power insufficient
    """

    orders: list[OptimizedOrder] = Field(
        description="List of orders to execute, sorted by priority (SELLs first)"
    )
    total_sell_proceeds: float = Field(
        ge=0,
        description="Estimated total proceeds from all SELL orders",
    )
    total_buy_cost: float = Field(
        ge=0,
        description="Estimated total cost of all BUY orders (after scaling)",
    )
    available_buying_power: float = Field(
        description="Available funds = current_buying_power + sell_proceeds",
    )
    scaling_applied: bool = Field(
        description="True if BUY orders were scaled down due to insufficient funds",
    )
    scaling_factor: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="If scaling applied, the factor (e.g., 0.75 = 75% of original)",
    )
    orders_skipped: int = Field(
        default=0,
        ge=0,
        description="Number of orders skipped (e.g., < 1 share after scaling)",
    )
    notes: str = Field(
        max_length=1000,
        description="Agent's explanation of adjustments and optimization reasoning",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "orders": [
                        {
                            "symbol": "TSLA",
                            "side": "sell",
                            "shares": 10,
                            "estimated_price": 275.50,
                            "estimated_cost": 2755.00,
                            "original_size_percent": 50,
                            "adjusted_size_percent": None,
                            "priority": 1,
                            "skip_reason": None,
                        },
                        {
                            "symbol": "AAPL",
                            "side": "buy",
                            "shares": 5,
                            "estimated_price": 185.00,
                            "estimated_cost": 925.00,
                            "original_size_percent": 10,
                            "adjusted_size_percent": 7,
                            "priority": 2,
                            "skip_reason": None,
                        },
                    ],
                    "total_sell_proceeds": 2755.00,
                    "total_buy_cost": 925.00,
                    "available_buying_power": 5255.00,
                    "scaling_applied": True,
                    "scaling_factor": 0.7,
                    "orders_skipped": 1,
                    "notes": "Scaled BUY orders to 70% due to limited buying power. Skipped MSFT buy (< 1 share after scaling).",
                }
            ]
        }
    }


class SymbolAnalysisResult(BaseModel):
    """
    Complete result from analyzing a single symbol.

    Phase 1 output: Pure research analysis without trading decisions.
    Decisions are made holistically in Phase 2.
    """

    symbol: str
    analysis_type: str  # "holding", "watchlist"
    analysis_text: str  # Full text response from ReAct agent
    analysis_id: str  # Unique ID for tracking
    chat_id: str  # Chat where analysis message was stored
    message_id: str | None = None  # Message ID if stored


class PortfolioDecisionList(BaseModel):
    """
    Phase 2: Batch trading decisions from Portfolio Agent.

    After all symbol analyses complete, the Portfolio Agent reviews everything
    holistically and outputs decisions for all symbols at once.
    """

    decisions: list[TradingDecision] = Field(
        description="List of trading decisions for all analyzed symbols"
    )
    portfolio_assessment: str = Field(
        max_length=1000,
        description="Overall portfolio assessment and optimization reasoning",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "decisions": [
                        {
                            "symbol": "AAPL",
                            "decision": "HOLD",
                            "position_size_percent": None,
                            "swap_from_symbol": None,
                            "confidence": 7,
                            "reasoning_summary": "Position already optimal, maintaining exposure",
                        },
                        {
                            "symbol": "TSLA",
                            "decision": "SELL",
                            "position_size_percent": 30,
                            "swap_from_symbol": None,
                            "confidence": 8,
                            "reasoning_summary": "Taking profits to rebalance, reducing concentration",
                        },
                        {
                            "symbol": "NVDA",
                            "decision": "BUY",
                            "position_size_percent": 15,
                            "swap_from_symbol": None,
                            "confidence": 8,
                            "reasoning_summary": "Adding AI exposure with available buying power",
                        },
                    ],
                    "portfolio_assessment": "Rebalancing to reduce TSLA concentration (was 35% of portfolio) and add diversification via NVDA. SELL proceeds fund BUY with remaining buying power.",
                }
            ]
        }
    }
