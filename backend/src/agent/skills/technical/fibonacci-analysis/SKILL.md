---
name: fibonacci-analysis
description: Calculate Fibonacci retracement levels and identify golden zone support/resistance
allowed-tools: get_historical_prices fibonacci_analysis_tool
metadata:
  domain: technical
  complexity: intermediate
---

## Fibonacci Analysis Workflow

OBJECTIVE: Identify key Fibonacci levels and assess price position.

### Step 1: Get Price Data
- Use `get_historical_prices` with 6-month lookback
- Identify the most significant swing (major high to low or low to high)

### Step 2: Calculate Fibonacci Levels
- Use `fibonacci_analysis_tool` with the identified swing points
- The tool will calculate: 23.6%, 38.2%, 50%, 61.8%, 78.6% levels

### Step 3: Focus on Golden Zone
- The 61.5%-61.8% level is the "golden ratio" - most significant
- For UPTREND: Golden zone is SUPPORT (price retraces down to it)
- For DOWNTREND: Golden zone is RESISTANCE (price bounces up to it)

### Step 4: Assess Current Position
- ABOVE golden zone: Bullish positioning
- IN golden zone: Critical decision area (watch for reversal signals)
- BELOW golden zone: Support broken, trend may be reversing

### Output Format
Fibonacci Analysis: [SYMBOL]
Swing: [TYPE] from $LOW to $HIGH
Golden Zone: $X.XX - $Y.YY
Current Price: $Z.ZZ -> [ABOVE/IN/BELOW] golden zone
Interpretation: [Actionable assessment]
