---
name: earnings-quality
description: Evaluate earnings trends, beat rate, and quality signals
allowed-tools: get_company_earnings get_financial_statements
metadata:
  domain: financial
  complexity: intermediate
---

## Earnings Quality Workflow

OBJECTIVE: Assess the quality and sustainability of earnings.

### Step 1: Get Earnings Data
- Use `get_company_earnings` for historical EPS and estimates
- Look at last 4-8 quarters of results

### Step 2: Beat/Miss Analysis
- How many quarters beat estimates? (> 75% is strong)
- Average surprise magnitude (consistent beats are better than volatile)
- Any recent misses? (recent misses are more concerning)

### Step 3: Growth Trajectory
- YoY EPS growth rate
- Is growth accelerating or decelerating?
- Forward estimates vs trailing (market expects what?)

### Step 4: Quality Signals
- Compare EPS growth to revenue growth (EPS growing faster suggests margin expansion)
- Compare earnings to operating cash flow (divergence is red flag)
- One-time items? Accounting adjustments?

### Output Format
Earnings Quality: [SYMBOL]
Beat Rate: {x}/{y} quarters | Avg Surprise: {pct}%
EPS Growth: {pct}% YoY | Trajectory: [ACCELERATING/STABLE/DECELERATING]
Quality: [HIGH/MODERATE/QUESTIONABLE]
Red Flags: [None/List any concerns]
