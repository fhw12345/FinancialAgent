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
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.models.derivations import Derivation


class TradingAction(StrEnum):
    """Trading action types."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    SWAP = "SWAP"


class OrderIntent(StrEnum):
    """Direction-aware intent. Disambiguates a SELL into either an exit of an
    existing long position (close_long, the common case in this portfolio
    flow) or a new short trade (open_short, rare). Necessary because the
    raw ``stop_loss``/``take_profit`` field layout is byte-identical for
    ``close_long`` and ``open_short`` and a downstream OMS would otherwise
    mis-route the order.
    """

    OPEN_LONG = "open_long"
    CLOSE_LONG = "close_long"
    OPEN_SHORT = "open_short"
    CLOSE_SHORT = "close_short"
    HOLD = "hold"


# ---------------------------------------------------------------------------
# W2.7 sub-models — structured research blocks attached to TradingDecision.
# All optional at the TradingDecision level; the validators here enforce
# *internal* shape whenever a block IS provided.
# ---------------------------------------------------------------------------


class ValuationMethod(BaseModel):
    """One arm of the valuation triangulation (per analyst PRD)."""

    method: Literal[
        "pe_vs_peer",
        "ev_revenue",
        "ev_ebitda",
        "peg",
        "dcf_quick",
        "p_book",
        "ps_ratio",
        "other",
    ] = Field(description="Which valuation framework was applied")
    value: float | None = Field(
        default=None,
        description=(
            "Numeric output (e.g. 'fair value' from DCF, or the ratio if "
            "method is pe_vs_peer). None when the method is purely "
            "qualitative (rare)."
        ),
    )
    note: str = Field(
        max_length=300,
        description=(
            "1-2 sentence justification, MUST cite the input data "
            "(e.g. 'AAPL trailing P/E 31 vs MAG7 median 28 → 11% premium')."
        ),
    )


class PriceTarget(BaseModel):
    value: float = Field(gt=0, description="Target price in USD")
    horizon_days: int = Field(
        ge=7,
        le=730,
        description="Time horizon (days) the target is for, e.g. 90 / 365.",
    )
    method: str | None = Field(
        default=None,
        max_length=120,
        description="Which valuation arm produced this PT (free-text label).",
    )


class ScenarioCase(BaseModel):
    price_target: float = Field(gt=0)
    probability: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Subjective probability of this scenario realising in the "
            "horizon. Per W2.10 the LLM is required to anchor the number "
            "to a base rate or historical frequency in `rationale`."
        ),
    )
    rationale: str = Field(
        max_length=300,
        description=(
            "Why this probability — should reference base rate / historical "
            "frequency / explicit conditioning, not just vibes."
        ),
    )


class ScenarioSet(BaseModel):
    """Bull / base / bear with probabilities summing to 1.0±0.02."""

    bull: ScenarioCase
    base: ScenarioCase
    bear: ScenarioCase

    @model_validator(mode="after")
    def _probabilities_sum_to_one(self) -> "ScenarioSet":
        total = self.bull.probability + self.base.probability + self.bear.probability
        if not (0.98 <= total <= 1.02):
            raise ValueError(
                f"scenario probabilities must sum to 1.0 (±0.02), got {total:.4f} "
                f"(bull={self.bull.probability}, base={self.base.probability}, "
                f"bear={self.bear.probability})"
            )
        return self


class Catalyst(BaseModel):
    event: str = Field(
        max_length=120,
        description="What is the catalyst (e.g. 'Q1 earnings', 'FOMC decision').",
    )
    eta_window: str = Field(
        max_length=80,
        description="When (e.g. '2026-05-15', 'next 2 weeks', 'Q3 2026').",
    )


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
    entry_price: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Limit-order price to enter the position. REQUIRED for BUY/SELL "
            "(use a price near current market that aligns with a support/"
            "resistance/fibonacci level from the tools); None for HOLD."
        ),
    )
    stop_loss: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Stop-loss price — exit if the trade moves against you. REQUIRED "
            "for BUY/SELL (anchor to a level the LLM saw in tools, e.g. swing "
            "low / fib 0.786); None for HOLD. Long-side intents (open_long, "
            "close_long): stop_loss < entry_price (protect from downside). "
            "Short-side intents (open_short, close_short): stop_loss > "
            "entry_price (protect from upside)."
        ),
    )
    take_profit: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Take-profit target price. REQUIRED for BUY/SELL (anchor to a "
            "tool-derived level, e.g. fib 1.618 extension / prior swing high); "
            "None for HOLD. Long-side intents: take_profit > entry_price. "
            "Short-side intents: take_profit < entry_price."
        ),
    )
    intent: OrderIntent | None = Field(
        default=None,
        description=(
            "Direction-aware intent. If omitted, inferred from `decision`: "
            "BUY -> open_long, SELL -> close_long (common case for portfolio "
            "rebalancing), HOLD -> hold. Set explicitly to `open_short` only "
            "when actually opening a new short position; the validator will "
            "then require stop_loss > entry_price (instead of < entry_price "
            "for close_long)."
        ),
    )
    # W2.7 — optional structured research blocks. All fields default to
    # None so existing Phase2 payloads still parse; the new Phase2 prompt
    # (W2.10) asks the LLM to populate them. Validators below enforce
    # length / probability rules whenever a block IS provided.
    thesis: list[str] | None = Field(
        default=None,
        description=(
            "Exactly 3 short bullet points summarising the investment thesis. "
            "If provided the validator requires len == 3 and each bullet "
            "non-empty; absent is allowed for backward compatibility."
        ),
    )
    valuation: list[ValuationMethod] | None = Field(
        default=None,
        description=(
            "At least 2 valuation methods (e.g. pe_vs_peer, ev_revenue, peg, "
            "dcf_quick). Required to triangulate; one method alone is "
            "rejected when the field is provided. Absent is allowed."
        ),
    )
    price_target: PriceTarget | None = Field(
        default=None,
        description="Optional 12-month-ish price target with horizon_days.",
    )
    scenarios: ScenarioSet | None = Field(
        default=None,
        description=(
            "bull / base / bear cases each with target + probability. "
            "Probabilities must sum to 1.0 (±0.02). Absent is allowed."
        ),
    )
    catalysts: list[Catalyst] | None = Field(
        default=None,
        description=(
            "Upcoming events that could move the stock in the next ~4 weeks. "
            "Absent is allowed."
        ),
    )
    risks: list[str] | None = Field(
        default=None,
        description=(
            "Top 3 risks ranked by importance. If provided the validator "
            "requires len == 3."
        ),
    )
    # W2.9 — optional per-number derivation audit trail. Each
    # *_derivation, when present, must satisfy `derivation.value ≈
    # corresponding price/size` within 0.5%; the validator below
    # enforces this so the LLM can't paper over a derivation that
    # disagrees with the headline number.
    entry_derivation: "Derivation | None" = Field(
        default=None,
        description="Audit trail for entry_price (formula + inputs).",
    )
    stop_derivation: "Derivation | None" = Field(
        default=None,
        description="Audit trail for stop_loss (e.g. atr_stop output).",
    )
    target_derivation: "Derivation | None" = Field(
        default=None,
        description="Audit trail for take_profit.",
    )
    size_derivation: "Derivation | None" = Field(
        default=None,
        description=(
            "Audit trail for position_size_percent — e.g. "
            "vol_adjusted_size mapped to a % of buying_power."
        ),
    )
    reasoning_summary: str = Field(
        max_length=1000,
        description=(
            "Brief reasoning. MUST cite the specific tool-derived levels you "
            "used to set entry_price/stop_loss/take_profit (e.g. 'Entry at "
            "fib 0.618=$182, stop below swing low $175, target at fib 1.618="
            "$210')."
        ),
    )

    @model_validator(mode="after")
    def _validate_intent_geometry(self) -> "TradingDecision":
        """Infer intent if absent and enforce stop/target geometry per intent.

        Geometry rules (price levels relative to entry_price):

        - open_long  / close_long  : stop_loss < entry < take_profit
        - open_short / close_short : stop_loss > entry > take_profit

        Any violation rejects the decision rather than silently shipping a
        payload whose field layout matches the wrong order intent (the
        CRWV-style hard bug from 2026-05-07: SELL with stop=142 > entry=138
        > target=122 reads as a short trade in any OMS).
        """
        if self.intent is None:
            inferred = {
                TradingAction.BUY: OrderIntent.OPEN_LONG,
                TradingAction.SELL: OrderIntent.CLOSE_LONG,
                TradingAction.HOLD: OrderIntent.HOLD,
                TradingAction.SWAP: OrderIntent.OPEN_LONG,
            }.get(self.decision)
            object.__setattr__(self, "intent", inferred)

        if self.intent == OrderIntent.HOLD:
            return self

        e, s, t = self.entry_price, self.stop_loss, self.take_profit
        if e is None or s is None or t is None:
            return self

        # Geometry follows the *position direction*, not the open/close action:
        # any long-side order (entering or exiting a long) protects with a
        # stop BELOW the entry/limit price; any short-side order protects
        # ABOVE. This is why CRWV's stop=142>entry=138>target=122 had to be
        # rejected: it was tagged close_long but used short-side geometry.
        long_side = self.intent in (OrderIntent.OPEN_LONG, OrderIntent.CLOSE_LONG)
        if long_side:
            if not (s < e < t):
                raise ValueError(
                    f"intent={self.intent.value} requires stop_loss < entry_price < "
                    f"take_profit, got stop={s} entry={e} target={t}"
                )
        else:
            if not (s > e > t):
                raise ValueError(
                    f"intent={self.intent.value} requires stop_loss > entry_price > "
                    f"take_profit, got stop={s} entry={e} target={t}"
                )
        return self

    @model_validator(mode="after")
    def _validate_research_blocks(self) -> "TradingDecision":
        """W2.7/W2.8 — enforce length rules whenever the optional research
        blocks are populated. Absent blocks are fine (back-compat)."""
        if self.thesis is not None:
            if len(self.thesis) != 3:
                raise ValueError(
                    f"thesis must contain exactly 3 bullet points, "
                    f"got {len(self.thesis)}"
                )
            if any(not (b and b.strip()) for b in self.thesis):
                raise ValueError("thesis bullets must be non-empty strings")

        if self.valuation is not None and len(self.valuation) < 2:
            raise ValueError(
                "valuation must contain at least 2 distinct methods for "
                f"triangulation, got {len(self.valuation)}"
            )

        if self.risks is not None and len(self.risks) != 3:
            raise ValueError(
                f"risks must contain exactly 3 ranked risks, got {len(self.risks)}"
            )
        return self

    @model_validator(mode="after")
    def _validate_derivation_consistency(self) -> "TradingDecision":
        """W2.9 — when a derivation is attached, its `value` must match the
        corresponding price/size within 0.5% (or exactly for size).
        Catches the failure mode where the LLM fills in a plausible
        formula but the headline number drifted from it."""
        pairs = [
            ("entry_derivation", "entry_price"),
            ("stop_derivation", "stop_loss"),
            ("target_derivation", "take_profit"),
        ]
        for d_attr, p_attr in pairs:
            d = getattr(self, d_attr)
            p = getattr(self, p_attr)
            if d is None or p is None:
                continue
            tol = max(abs(p) * 0.005, 0.01)
            if abs(d.value - p) > tol:
                raise ValueError(
                    f"{d_attr}.value ({d.value}) does not match {p_attr} "
                    f"({p}) within 0.5% tolerance"
                )
        # size_derivation: numeric drift is OK but value must be >= 0.
        if self.size_derivation is not None and self.size_derivation.value < 0:
            raise ValueError("size_derivation.value cannot be negative")
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "AAPL",
                    "decision": "BUY",
                    "position_size_percent": 10,
                    "swap_from_symbol": None,
                    "confidence": 8,
                    "entry_price": 182.50,
                    "stop_loss": 175.00,
                    "take_profit": 210.00,
                    "reasoning_summary": (
                        "Entry at fib 0.618 retracement ($182.50). Stop below "
                        "swing low ($175). Target at fib 1.618 extension ($210)."
                    ),
                },
                {
                    "symbol": "TSLA",
                    "decision": "SELL",
                    "position_size_percent": 50,
                    "swap_from_symbol": None,
                    "confidence": 7,
                    "entry_price": 278.00,
                    "stop_loss": 260.00,
                    "take_profit": 295.00,
                    "intent": "close_long",
                    "reasoning_summary": (
                        "Sell 50% of long at recovery $278. Stop at $260 if "
                        "rebound fails (below 50DMA). Let remainder run to "
                        "$295 prior swing high if uptrend resumes."
                    ),
                },
                {
                    "symbol": "NVDA",
                    "decision": "HOLD",
                    "position_size_percent": None,
                    "swap_from_symbol": None,
                    "confidence": 6,
                    "entry_price": None,
                    "stop_loss": None,
                    "take_profit": None,
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

    consistency_passed: bool | None = None
    consistency_violations: list[dict[str, Any]] = Field(default_factory=list)
    degraded_fields: list[str] = Field(default_factory=list)


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
                            "entry_price": None,
                            "stop_loss": None,
                            "take_profit": None,
                            "reasoning_summary": "Position already optimal, maintaining exposure",
                        },
                        {
                            "symbol": "TSLA",
                            "decision": "SELL",
                            "position_size_percent": 30,
                            "swap_from_symbol": None,
                            "confidence": 8,
                            "entry_price": 278.00,
                            "stop_loss": 260.00,
                            "take_profit": 295.00,
                            "intent": "close_long",
                            "reasoning_summary": (
                                "Trim 30% at recovery $278. Stop $260 if "
                                "rebound fails (50DMA). Let remainder run to "
                                "$295 prior swing high if uptrend resumes."
                            ),
                        },
                        {
                            "symbol": "NVDA",
                            "decision": "BUY",
                            "position_size_percent": 15,
                            "swap_from_symbol": None,
                            "confidence": 8,
                            "entry_price": 132.00,
                            "stop_loss": 124.00,
                            "take_profit": 156.00,
                            "reasoning_summary": (
                                "Entry at fib 0.5 ($132). Stop below swing low "
                                "($124). Target at prior high ($156)."
                            ),
                        },
                    ],
                    "portfolio_assessment": "Rebalancing to reduce TSLA concentration (was 35% of portfolio) and add diversification via NVDA. SELL proceeds fund BUY with remaining buying power.",
                }
            ]
        }
    }
