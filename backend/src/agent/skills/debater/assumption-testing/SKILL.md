---
name: assumption-testing
description: Challenge the underlying assumptions in the investment thesis
allowed-tools: fetch_yfinance_news search_web_exa
metadata:
  domain: debater
  complexity: advanced
---

## Assumption Testing Workflow

OBJECTIVE: Validate or invalidate key assumptions using INDEPENDENT data sources.

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

Use your independent tools:
- `fetch_yfinance_news` for current stats vs assumed (actual PE, EPS, growth rates)
- `search_web_exa` for competitive dynamics, industry trends, analyst consensus

CRITICAL: Compare what the thesis ASSUMES against what your INDEPENDENT sources show. The research used Alpha Vantage data — you are cross-checking with different sources.

### Step 3: Sensitivity Analysis
If assumption is wrong, what happens to thesis?
- Thesis still valid? (robust assumption)
- Thesis weakened? (sensitive assumption)
- Thesis invalidated? (critical assumption)

### Output Format
ASSUMPTION TEST: [SYMBOL]

CRITICAL ASSUMPTIONS (thesis depends on these):
1. Assumption: [Statement]
   Supporting Evidence: [Independent data]
   Contradicting Evidence: [Independent data]
   If Wrong: [Impact on thesis]
   Verdict: [SOLID/QUESTIONABLE/WEAK]

SENSITIVE ASSUMPTIONS (would weaken thesis if wrong):
[Same format]

ROBUST ASSUMPTIONS (thesis valid even if wrong):
[Same format]

WEAKEST LINK: [Most questionable critical assumption]
