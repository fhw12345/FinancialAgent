---
name: momentum-signals
description: Analyze Stochastic oscillator for momentum signals and divergences
allowed-tools: stochastic_analysis_tool get_historical_prices
metadata:
  domain: technical
  complexity: intermediate
---

## Momentum Signals Workflow

OBJECTIVE: Assess momentum health and identify potential reversals.

### Step 1: Get Stochastic Readings
- Use `stochastic_analysis_tool` for current %K and %D values
- Default settings: K=14, D=3

### Step 2: Classify Zone
- OVERBOUGHT: %K > 80 (price may be extended, watch for reversal)
- OVERSOLD: %K < 20 (price may be depressed, watch for bounce)
- NEUTRAL: 20 < %K < 80 (no extreme)

### Step 3: Check Crossovers
- BULLISH CROSSOVER: %K crosses above %D (buy signal)
- BEARISH CROSSOVER: %K crosses below %D (sell signal)
- NO CROSSOVER: Watch for setup

### Step 4: Divergence Check
- BULLISH DIVERGENCE: Price makes lower low, but %K makes higher low
- BEARISH DIVERGENCE: Price makes higher high, but %K makes lower high
- These are powerful reversal signals

### Output Format
Stochastic: %K={value}, %D={value}
Zone: [OVERBOUGHT/OVERSOLD/NEUTRAL]
Signal: [BULLISH CROSSOVER/BEARISH CROSSOVER/NONE]
Divergence: [YES - TYPE/NONE DETECTED]
Interpretation: [Actionable assessment]
