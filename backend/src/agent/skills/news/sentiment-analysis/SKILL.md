---
name: sentiment-analysis
description: Aggregate and analyze news sentiment for a stock symbol
allowed-tools: get_news_sentiment
metadata:
  domain: news
  complexity: basic
---

## Sentiment Analysis Workflow

OBJECTIVE: Determine overall news sentiment and key themes for the symbol.

### Step 1: Gather Recent News
- Use `get_news_sentiment` with max_results=10
- Focus on news from the past 7 days

### Step 2: Classify Each Item
For each news item, classify as:
- POSITIVE: Bullish news (earnings beat, upgrades, product launches)
- NEGATIVE: Bearish news (misses, downgrades, lawsuits, delays)
- NEUTRAL: Informational without clear sentiment

### Step 3: Calculate Aggregate Score
- Count: X positive, Y negative, Z neutral
- Score = (positive - negative) / total
- Score > 0.3: BULLISH sentiment
- Score < -0.3: BEARISH sentiment
- Otherwise: MIXED sentiment

### Step 4: Identify Themes
- What topics appear repeatedly?
- Any developing narratives?
- Institutional vs retail focus?

### Output Format
Sentiment Score: [+X.XX or -X.XX] -> [BULLISH/BEARISH/MIXED]
Distribution: {positive} positive, {negative} negative, {neutral} neutral
Key Themes:
1. [Theme 1 with example headline]
2. [Theme 2 with example headline]
Dominant Narrative: [Summary of overall story]
