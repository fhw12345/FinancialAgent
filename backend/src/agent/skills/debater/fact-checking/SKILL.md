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

### Step 4: Compile Report
List claims with verification status and source references.

### Output Format
FACT CHECK REPORT: [SYMBOL] Thesis

VERIFIED CLAIMS:
- [Claim] - Source: [Yahoo Finance / Exa web search]

QUESTIONABLE CLAIMS:
? [Claim] - Issue: [what's wrong] - Source: [reference]

CONTRADICTED CLAIMS:
x [Claim] - Reality: [what independent sources show] - Source: [reference]

ACCURACY SCORE: {verified}/{total} claims verified
