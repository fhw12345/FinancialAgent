---
name: risk-assessment
description: Identify risk factors not adequately addressed in the thesis
allowed-tools: get_insider_activity get_financial_statements get_news_sentiment get_market_movers get_put_call_ratio
metadata:
  domain: debater
  complexity: advanced
---

## Risk Assessment Workflow

OBJECTIVE: Find risks the thesis may have overlooked or underweighted.

### Step 1: Catalog Mentioned Risks
What risks did the thesis acknowledge?
- Keep a list to avoid duplicating

### Step 2: Check Standard Risk Categories
Use tools to check for these common risks:

COMPANY-SPECIFIC:
- Use `get_insider_activity` for insider selling (red flag if heavy)
- Use `get_financial_statements` for debt concerns
- Use `get_news_sentiment` for litigation, regulatory issues

MARKET/SECTOR:
- Use `get_market_movers` for sector weakness
- Check if sector is leading or lagging

SENTIMENT:
- Use `get_put_call_ratio` for unusual options activity
- High PCR = market betting against stock

### Step 3: Gap Analysis
Which of these risks were NOT mentioned in thesis?
- Completely missing?
- Mentioned but underweighted?

### Output Format
RISK ASSESSMENT: [SYMBOL]

RISKS MENTIONED IN THESIS:
- [List from thesis]

POTENTIALLY OVERLOOKED RISKS:
1. [Risk Category]: [Specific finding]
   Evidence: [Tool output]
   Severity: [HIGH/MEDIUM/LOW]

2. [Next risk...]

RISK MATRIX:
| Risk | Mentioned? | Severity | Status |
|------|-----------|----------|--------|
| ...  | ...       | ...      | ...    |

BIGGEST GAP: [Most significant overlooked risk]
