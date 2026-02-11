---
name: cashflow-health
description: Assess cash flow generation, debt levels, and financial stability
allowed-tools: get_financial_statements get_company_overview
metadata:
  domain: financial
  complexity: intermediate
---

## Cash Flow Health Workflow

OBJECTIVE: Evaluate the company's financial strength and sustainability.

### Step 1: Get Financial Data
- Use `get_financial_statements` for balance sheet and cash flow
- Focus on: Operating CF, Free CF, Debt levels, Cash position

### Step 2: Cash Flow Quality
- Is operating cash flow positive and growing?
- Is FCF (Free Cash Flow) positive? FCF = Operating CF - CapEx
- FCF Margin = FCF / Revenue (higher is better, >15% is strong)

### Step 3: Debt Analysis
- Debt/Equity ratio (< 1 is conservative, > 2 is aggressive)
- Interest coverage (EBIT / Interest Expense, > 5 is comfortable)
- Net debt position (Total Debt - Cash)

### Step 4: Liquidity Assessment
- Current ratio (Current Assets / Current Liabilities, > 1.5 is healthy)
- Quick ratio (excludes inventory, > 1 is good)

### Output Format
Financial Health: [SYMBOL]
FCF: ${amount} | FCF Margin: {pct}% -> [STRONG/MODERATE/WEAK]
Debt/Equity: {ratio} | Interest Coverage: {x}x
Net Debt: ${amount} | Liquidity: [AMPLE/ADEQUATE/TIGHT]
Overall: [FORTRESS/HEALTHY/MANAGEABLE/CONCERNING]
