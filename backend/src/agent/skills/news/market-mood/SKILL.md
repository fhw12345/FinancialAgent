---
name: market-mood
description: Assess overall market sentiment and how the target stock fits
allowed-tools: get_market_movers
metadata:
  domain: news
  complexity: basic
---

## Market Mood Workflow

OBJECTIVE: Understand the broader market context for the analysis.

### Step 1: Get Market Overview
- Use `get_market_movers` for today's gainers/losers
- Identify which sectors are leading/lagging

### Step 2: Classify Market Environment
- RISK-ON: Tech and growth leading, defensive lagging
- RISK-OFF: Utilities, healthcare leading, tech lagging
- ROTATION: Sector-specific moves, not broad trend
- MIXED: No clear pattern

### Step 3: Sector Context
- Which sector is the target stock in?
- Is that sector leading, lagging, or neutral today?
- Any sector-specific news driving moves?

### Step 4: Positioning Assessment
- If target is in a leading sector: Tailwind for the stock
- If target is in a lagging sector: Headwind to overcome
- If target is outperforming its sector: Stock-specific strength

### Output Format
Market Environment: [RISK-ON/RISK-OFF/ROTATION/MIXED]
Sector Performance: [Target's sector] is [LEADING/LAGGING/NEUTRAL]
Top Movers: [Notable names and why]
Context for {SYMBOL}: [How does market context affect the stock?]
