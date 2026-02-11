---
name: assumption-testing
description: Challenge the underlying assumptions in the investment thesis
allowed-tools: get_company_overview get_company_earnings get_news_sentiment get_market_movers
metadata:
  domain: debater
  complexity: advanced
---

## Assumption Testing Workflow

OBJECTIVE: Validate or invalidate key assumptions underlying the thesis.

### Step 1: Extract Assumptions
Identify both explicit and implicit assumptions:
- Growth rate assumptions ("revenue will grow X%")
- Market assumptions ("sector will outperform")
- Competitive assumptions ("moat is sustainable")
- Valuation assumptions ("multiple will expand")
- Macro assumptions ("economy stays strong")

### Step 2: Test Each Assumption
For each assumption:
- What evidence supports it?
- What evidence contradicts it?
- What would invalidate it?

Use tools:
- `get_company_overview` for current state vs assumed
- `get_company_earnings` for actual vs projected growth
- `get_news_sentiment` for competitive dynamics
- `get_market_movers` for sector trends

### Step 3: Sensitivity Analysis
If assumption is wrong, what happens to thesis?
- Thesis still valid? (robust assumption)
- Thesis weakened? (sensitive assumption)
- Thesis invalidated? (critical assumption)

### Output Format
ASSUMPTION TEST: [SYMBOL]

CRITICAL ASSUMPTIONS (thesis depends on these):
1. Assumption: [Statement]
   Supporting Evidence: [Data]
   Contradicting Evidence: [Data]
   If Wrong: [Impact on thesis]
   Verdict: [SOLID/QUESTIONABLE/WEAK]

SENSITIVE ASSUMPTIONS (would weaken thesis if wrong):
[Same format]

ROBUST ASSUMPTIONS (thesis valid even if wrong):
[Same format]

WEAKEST LINK: [Most questionable critical assumption]
