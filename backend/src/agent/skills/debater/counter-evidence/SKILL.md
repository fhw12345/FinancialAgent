---
name: counter-evidence
description: Search for evidence that contradicts the investment thesis using independent sources
allowed-tools: fetch_yfinance_news search_web_exa
metadata:
  domain: debater
  complexity: advanced
---

## Counter Evidence Workflow

OBJECTIVE: Find legitimate reasons why the thesis might be wrong, using INDEPENDENT data sources.

### Step 1: Identify Thesis Pillars
What are the key bullish arguments?
- Growth assumptions (revenue, earnings, market share)
- Competitive advantages (moat, technology, brand)
- Market opportunity claims (TAM, growth rate)
- Management quality assertions
- Valuation justification

### Step 2: Targeted Counter-Search
For each pillar, actively look for contradictions:
- Use `search_web_exa` with bearish keywords:
  - "[company] risks", "[company] challenges", "[company] lawsuit"
  - "[company] competition losing", "[company] regulatory action"
  - "[company] analyst downgrade", "[company] SEC investigation"
- Use `fetch_yfinance_news` to check:
  - Whether financial stats match the thesis claims
  - Recent news headlines that contradict the bullish narrative
  - Key stats (PE ratio, growth rates) vs thesis assumptions

### Step 3: Assess Severity
Rate each counter-evidence found:
- MINOR: Doesn't invalidate thesis, manageable risk
- MAJOR: Potentially invalidates key thesis pillar

### Output Format
Return one JSON object only, without Markdown fences:

{"concerns":[{"id":"C1","claim":"Claim being challenged","category":"technical|fundamental|valuation|risk","challenge":"Evidence-based challenge","severity":"MAJOR|MINOR","evidence":"Independent source"}]}
