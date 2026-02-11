---
name: fact-checking
description: Verify specific claims in the thesis against authoritative sources
allowed-tools: get_news_sentiment get_company_overview get_company_earnings get_financial_statements
metadata:
  domain: debater
  complexity: intermediate
---

## Fact Checking Workflow

OBJECTIVE: Verify factual accuracy of claims in the investment thesis.

### Step 1: Extract Claims
Identify specific factual assertions in the thesis:
- Price targets and levels mentioned
- Earnings figures, revenue numbers, growth rates
- News events, announcements, dates
- Comparative statements ("better than competitors")

### Step 2: Verify Each Claim
For each claim, use appropriate tools:
- Use `get_news_sentiment` for news/announcement verification
- Use `get_company_overview` for fundamental metrics
- Use `get_company_earnings` for earnings data
- Use `get_financial_statements` for financial statements

### Step 3: Classification
For each claim, classify as:
- VERIFIED: Matches authoritative sources
- PARTIALLY VERIFIED: Generally correct but details differ
- UNVERIFIED: Cannot find supporting evidence
- CONTRADICTED: Sources show different data
- OUTDATED: Was true but situation has changed

### Step 4: Compile Report
List claims with verification status and source references.

### Output Format
FACT CHECK REPORT: [SYMBOL] Thesis

VERIFIED CLAIMS:
- [Claim] - Source: [reference]

QUESTIONABLE CLAIMS:
? [Claim] - Issue: [what's wrong] - Source: [reference]

CONTRADICTED CLAIMS:
x [Claim] - Reality: [what sources show] - Source: [reference]

ACCURACY SCORE: {verified}/{total} claims verified
