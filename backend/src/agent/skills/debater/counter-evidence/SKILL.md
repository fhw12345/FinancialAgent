---
name: counter-evidence
description: Search for evidence that contradicts the investment thesis
allowed-tools: get_news_sentiment get_insider_activity get_put_call_ratio get_market_movers
metadata:
  domain: debater
  complexity: advanced
---

## Counter Evidence Workflow

OBJECTIVE: Find legitimate reasons why the thesis might be wrong.

### Step 1: Identify Thesis Pillars
What are the key bullish arguments?
- Growth assumptions (revenue, earnings, market share)
- Competitive advantages (moat, technology, brand)
- Market opportunity claims (TAM, growth rate)
- Management quality assertions
- Valuation justification

### Step 2: Targeted Counter-Search
For each pillar, actively look for contradictions:
- Use `get_news_sentiment` with bearish keywords:
  - "[company] risks", "[company] challenges", "[company] problems"
  - "[company] competition", "[company] losing", "[company] decline"
- Use `get_insider_activity` for insider selling
- Use `get_put_call_ratio` for options market sentiment (high PCR = bearish bets)

### Step 3: Assess Severity
Rate each counter-evidence found:
- MINOR: Doesn't invalidate thesis, manageable risk
- MODERATE: Reduces conviction, needs monitoring
- MAJOR: Potentially invalidates key thesis pillar
- CRITICAL: Fundamental flaw, thesis may be wrong

### Output Format
COUNTER EVIDENCE REPORT: [SYMBOL]

THESIS PILLAR: [Growth assumption]
Counter-Evidence: [What was found]
Severity: [MINOR/MODERATE/MAJOR/CRITICAL]
Implication: [What this means for the thesis]

---
[Repeat for each pillar]
---

OVERALL ASSESSMENT:
Thesis Vulnerability: [LOW/MODERATE/HIGH]
Most Concerning Finding: [Single biggest issue]
