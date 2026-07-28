---
name: risk-assessment
description: Identify risk factors not adequately addressed in the thesis
allowed-tools: fetch_yfinance_news search_web_exa
metadata:
  domain: debater
  complexity: advanced
---

## Risk Assessment Workflow

OBJECTIVE: Find risks the thesis may have overlooked or underweighted, using INDEPENDENT data sources.

### Step 1: Catalog Mentioned Risks
What risks did the thesis acknowledge?
- Keep a list to avoid duplicating

### Step 2: Check Standard Risk Categories
Use your independent tools to check for these common risks:

COMPANY-SPECIFIC:
- Use `fetch_yfinance_news` for financial health indicators (debt levels via key stats, earnings trends)
- Use `search_web_exa` for litigation, regulatory issues, executive departures

MARKET/SECTOR:
- Use `search_web_exa` for sector weakness, competitive threats, industry disruption
- Use `fetch_yfinance_news` for 52-week range positioning (near highs = less upside, near lows = why?)

SENTIMENT:
- Use `search_web_exa` for analyst downgrades, institutional selling reports
- Use `fetch_yfinance_news` for recent negative news headlines

### Step 3: Gap Analysis
Which of these risks were NOT mentioned in thesis?
- Completely missing?
- Mentioned but underweighted?

### Output Format
Return one JSON object only, without Markdown fences:

{"concerns":[{"id":"C1","claim":"Risk assumption being challenged","category":"risk","challenge":"Specific overlooked or underweighted risk","severity":"MAJOR|MINOR","evidence":"Independent source"}]}
