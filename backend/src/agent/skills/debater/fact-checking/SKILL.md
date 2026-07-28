---
name: fact-checking
description: Verify specific claims in the thesis against independent sources
allowed-tools: fetch_yfinance_news search_web_exa
metadata:
  domain: debater
  complexity: intermediate
---

## Fact Checking Workflow

OBJECTIVE: Cross-verify factual claims using INDEPENDENT data sources (not the same APIs the research used).

### Step 1: Extract Claims
Identify specific factual assertions in the thesis:
- Price targets and levels mentioned
- Earnings figures, revenue numbers, growth rates
- News events, announcements, dates
- Comparative statements ("better than competitors")

### Step 2: Verify Each Claim
For each claim, use your independent tools:
- Use `fetch_yfinance_news` for financial stats (PE ratio, EPS, revenue growth) and recent news
- Use `search_web_exa` for news events, announcements, lawsuits, regulatory actions

CRITICAL: These tools pull from DIFFERENT data sources than the research. If research says "EPS grew 22.9%" but Yahoo Finance shows different numbers, that's a discrepancy worth flagging.

### Step 3: Classification
For each claim, classify as:
- VERIFIED: Independent source confirms the claim
- PARTIALLY VERIFIED: Generally correct but details differ
- UNVERIFIED: Cannot find supporting evidence from independent sources
- CONTRADICTED: Independent sources show different data
- OUTDATED: Was true but situation has changed

### Output Format
Return one JSON object only, without Markdown fences:

{"concerns":[{"id":"C1","claim":"Factual claim being challenged","category":"technical|fundamental|valuation|risk","challenge":"Independent verification result","severity":"MAJOR|MINOR","evidence":"Independent source"}]}
