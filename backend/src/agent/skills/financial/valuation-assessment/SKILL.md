---
name: valuation-assessment
description: Analyze valuation metrics (P/E, PEG, P/S) to assess fair value
allowed-tools: get_company_overview
metadata:
  domain: financial
  complexity: basic
---

## Valuation Assessment Workflow

OBJECTIVE: Determine if the stock is attractively valued.

### Step 1: Get Valuation Metrics
- Use `get_company_overview` for current metrics:
  - P/E Ratio (trailing and forward)
  - PEG Ratio (growth-adjusted P/E)
  - Price/Sales, Price/Book
  - EV/EBITDA

### Step 2: Context Analysis
- Compare P/E to sector average (is it premium or discount?)
- Check forward P/E vs trailing (market expects growth or decline?)
- PEG < 1 suggests undervalued; PEG > 2 suggests expensive

### Step 3: Valuation Verdict
- UNDERVALUED: Multiple metrics below sector, strong fundamentals
- FAIR VALUE: Metrics in line with sector and growth
- OVERVALUED: Premium valuation needs justification
- SPECULATIVE: High multiples require exceptional growth

### Output Format
Valuation Summary: [SYMBOL]
P/E: {trailing} (TTM) | {forward} (FWD) | Sector Avg: {sector}
PEG Ratio: {peg} -> [ATTRACTIVE/FAIR/EXPENSIVE]
Verdict: [UNDERVALUED/FAIR/OVERVALUED/SPECULATIVE]
Key Insight: [Why this valuation makes sense or doesn't]
