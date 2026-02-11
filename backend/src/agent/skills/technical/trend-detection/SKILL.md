---
name: trend-detection
description: Identify the primary trend direction and strength using price action
allowed-tools: get_historical_prices stochastic_analysis_tool
metadata:
  domain: technical
  complexity: basic
---

## Trend Detection Workflow

OBJECTIVE: Determine the dominant market trend for the target symbol.

### Step 1: Gather Historical Data
- Use `get_historical_prices` with 3-month lookback (period="3mo")
- Identify swing highs and swing lows in the data

### Step 2: Classify Trend Structure
- UPTREND: Higher highs AND higher lows
- DOWNTREND: Lower highs AND lower lows
- SIDEWAYS: Mixed or no clear pattern

### Step 3: Confirm with Momentum
- Use `stochastic_analysis_tool` to check momentum alignment
- Trend + aligned momentum = STRONG trend
- Trend + diverging momentum = WEAKENING trend

### Step 4: Identify Key Levels
- In uptrend: Note last higher low as support
- In downtrend: Note last lower high as resistance

### Output Format
Trend: [UPTREND/DOWNTREND/SIDEWAYS] | Strength: [STRONG/MODERATE/WEAK]
Key Support: $X.XX | Key Resistance: $Y.YY
Momentum: [ALIGNED/DIVERGING] with trend
