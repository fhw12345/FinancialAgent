---
title: Portfolio Agent Architecture Refactor
status: shipped
version: backend@0.10.x+
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/src/services/watchlist/analysis.py
  - backend/src/services/watchlist/order_handler.py
  - backend/src/services/watchlist_analyzer.py
---

# Portfolio Agent Architecture Refactor

## Context

The previous portfolio analysis cron job had inefficient agent orchestration:
- Each symbol analysis included portfolio context and made 2 LLM calls (ainvoke + ainvoke_structured)
- Individual symbols made portfolio decisions in isolation
- Market movers were analyzed but excluded from execution (waste)
- All symbol analyses shared the same trace name, making structured-log triage confusing

## Problem Statement

1. **Inefficient**: 29 agent calls for 14 symbols (14 ainvoke + 14 ainvoke_structured + 1 aggregation)
2. **Poor Decision Quality**: Each symbol gets individual portfolio-aware decision before seeing other analyses
3. **Confusing Traces**: All symbol analyses named "Portfolio Optimization Analysis" in structured logs
4. **Wasted Compute**: Market movers analyzed but never executed

## Proposed Solution

### New Architecture: Research → Decide

```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: Independent Symbol Research (Concurrent)               │
│                                                                 │
│ For each symbol (holdings + watchlist only):                   │
│   └─ ainvoke() - Pure technical/fundamental analysis            │
│       • NO portfolio context                                    │
│       • NO ainvoke_structured()                                 │
│       • Returns: Raw analysis text                              │
│                                                                 │
│ Trace Name: "Symbol Research: {SYMBOL}"                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 2: Portfolio Agent Decision (Single Call)                 │
│                                                                 │
│ Input:                                                          │
│   • All symbol analyses from Phase 1                            │
│   • Current holdings (symbol, quantity, market_value, P/L%)     │
│   • Account summary (equity, buying_power, cash)                │
│                                                                 │
│ Output: List[TradingDecision]                                   │
│   • symbol: str                                                 │
│   • decision: BUY | SELL | HOLD                                 │
│   • position_size_percent: float                                │
│   • reasoning: str (short, packed)                              │
│                                                                 │
│ Trace Name: "Portfolio Decision"                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 3: Order Execution (Sequential)                           │
│                                                                 │
│ 1. SELL orders first (gain liquidity → increase buying power)   │
│ 2. Calculate available funds after SELLs                        │
│ 3. BUY orders (scale if insufficient funds)                     │
│                                                                 │
│ Clear distinction:                                              │
│   • SELL existing holding → Gain liquidity                      │
│   • SHORT position → Different handling (future)                │
│   • BUY new position → Use buying power                         │
│   • BUY more of holding → Add to position                       │
└─────────────────────────────────────────────────────────────────┘
```

### Key Changes

| Aspect | Current | New |
|--------|---------|-----|
| **Phase 1 Calls** | 14 ainvoke + 14 ainvoke_structured | 14 ainvoke only |
| **Phase 1 Context** | Includes portfolio info | Pure research, no portfolio |
| **Phase 1 Output** | SymbolAnalysisResult with TradingDecision | Raw analysis text only |
| **Market Movers** | Analyzed (9 symbols) | Removed entirely |
| **Phase 2 Input** | Individual TradingDecisions | All analyses + portfolio state |
| **Phase 2 Output** | OrderExecutionPlan | List[TradingDecision] |
| **Decision Point** | Per symbol (fragmented) | Single holistic decision |
| **Total LLM Calls** | 29 | 15 (5 holdings+watchlist + 1 decision) |

### Efficiency Improvement

**Before (2 holdings, 3 watchlist, 9 market movers = 14 symbols):**
- Phase 1: 14 × ainvoke = 14 calls
- Phase 1: 14 × ainvoke_structured = 14 calls
- Phase 2: 1 × ainvoke_structured = 1 call
- **Total: 29 LLM calls**

**After (2 holdings, 3 watchlist, 0 market movers = 5 symbols):**
- Phase 1: 5 × ainvoke = 5 calls
- Phase 2: 1 × ainvoke_structured = 1 call
- **Total: 6 LLM calls** (79% reduction)

## Implementation Plan

### Step 1: Update Phase 1 Prompt (Symbol Research)

**File**: `backend/src/agent/portfolio_analysis_agent.py`

Remove portfolio context from `_analyze_symbol()` prompt:

```python
# NEW: Pure research prompt, no portfolio context
prompt = f"""# Symbol Research: {symbol}

Conduct comprehensive technical and fundamental analysis for {symbol}.

## Analysis Requirements

1. **Technical Analysis**
   - Fibonacci retracement levels, trend analysis
   - Support/resistance levels, momentum indicators
   - Recent price action and volume patterns

2. **Fundamental Analysis**
   - Company financials, earnings quality
   - News sentiment, industry trends
   - Competitive position, growth prospects

3. **Value Assessment**
   - Current valuation vs intrinsic value
   - Risk factors and catalysts
   - Short-term vs long-term outlook

Provide factual analysis only. Do NOT make buy/sell recommendations.
Response in Simplified Chinese.
"""
```

### Step 2: Remove ainvoke_structured() from Phase 1

**File**: `backend/src/agent/portfolio_analysis_agent.py`

Remove the decision extraction call in `_analyze_symbol()`:
- Delete lines 906-950 (ainvoke_structured for TradingDecision)
- Return only analysis text, not SymbolAnalysisResult with decision

### Step 3: Remove Market Movers

**File**: `backend/src/agent/portfolio_analysis_agent.py`

- Remove market movers fetching (lines 266-310)
- Remove market movers analysis loop (lines 491-558)
- Update result_summary to exclude market_movers_analyzed

### Step 4: Create New Phase 2 Decision Method

**File**: `backend/src/agent/portfolio_analysis_agent.py`

New method for holistic portfolio decision:

```python
async def _make_portfolio_decisions(
    self,
    symbol_analyses: dict[str, str],  # {symbol: analysis_text}
    portfolio_context: dict[str, Any],
    user_id: str,
) -> list[TradingDecision]:
    """
    Phase 2: Make all trading decisions in a single holistic call.

    Input: All symbol analyses + portfolio state
    Output: List of TradingDecision for all symbols
    """
    # Build comprehensive prompt with all analyses
    prompt = f"""# Portfolio Trading Decisions

You are a portfolio manager. Based on the research below, make trading decisions
for each symbol considering the overall portfolio optimization.

## Current Portfolio State
- Total Equity: ${portfolio_context['total_equity']:,.2f}
- Buying Power: ${portfolio_context['buying_power']:,.2f}
- Cash: ${portfolio_context['cash']:,.2f}

## Current Holdings
{self._format_positions_table(portfolio_context['positions'])}

## Symbol Research Results
{self._format_all_analyses(symbol_analyses)}

## Decision Rules
- SELL: Specify % of current holding to sell (gain liquidity first)
- BUY: Specify % of buying power to spend
- HOLD: No action needed

For each analyzed symbol, provide:
- Decision (BUY/SELL/HOLD)
- Position size percentage
- Short reasoning (1-2 sentences)

Consider: portfolio diversification, risk management, liquidity needs.
"""

    # Single structured call for all decisions
    decisions = await self.react_agent.ainvoke_structured(
        prompt=prompt,
        schema=TradingDecisionList,  # New schema: List[TradingDecision]
        context=None,
    )

    return decisions.decisions
```

### Step 5: Update TradingDecision Schema

**File**: `backend/src/models/trading_decision.py`

Add new schema for batch decisions:

```python
class TradingDecisionList(BaseModel):
    """List of trading decisions from portfolio agent."""
    decisions: list[TradingDecision]
    portfolio_summary: str | None = None  # Optional overall assessment
```

### Step 6: Update Order Execution Clarity

**File**: `backend/src/agent/order_optimizer.py`

Add clearer liquidity handling:

```python
# Clarify order types in execution
for order in sorted_orders:
    if order.side == "sell":
        # SELL existing holding → Gain liquidity
        logger.info("Selling to gain liquidity", symbol=order.symbol)
    elif order.side == "buy":
        # BUY with available buying power
        logger.info("Buying with available funds", symbol=order.symbol)
```

## Acceptance Criteria

1. **Phase 1**: Each symbol analyzed independently without portfolio context
2. **Phase 1**: No ainvoke_structured() calls per symbol
3. **Phase 1**: Market movers completely removed
4. **Phase 2**: Single ainvoke_structured() returns List[TradingDecision]
5. **Phase 2**: All decisions made holistically with full portfolio visibility
6. **Phase 3**: SELLs execute first to gain liquidity before BUYs
7. **Observability**: Clear log trace names — "Symbol Research: X" vs "Portfolio Decision"
8. **Efficiency**: Total LLM calls reduced from 29 to ~6 for typical portfolio

## Migration Notes

- No database schema changes required
- Message storage format unchanged (analysis text stored per symbol)
- Order execution logic remains compatible
- Backward compatible with existing chat history

## Testing Plan

1. Dry-run with `dry_run=True` to verify flow
2. Check structured log traces for correct naming
3. Verify decision quality with test portfolio
4. Confirm order execution sequence (SELLs before BUYs)
