# Debate Quality Improvement Design

**Date:** 2026-02-23
**Status:** Approved
**Branch:** TBD (from origin/main)

## Problem Statement

Analysis of a real AAPL deep analysis debate (chat `chat_794c7f8f7403`, 2026-02-22) revealed 5 concrete quality problems:

1. **Sub-agents don't share data** — News analyst found CSAM lawsuits, but the financial analyst in rebuttal couldn't find them and called the claim "fabricated."
2. **Verdict made factual errors** — The -62% EPS was correctly identified as a fiscal-quarter-vs-annual artifact by the rebuttal, yet the verdict marked it "VERIFIED" (rubber-stamping the debater's last word).
3. **Asymmetric debate** — Debater gets the last word (Round 2 attack → verdict). No rebuttal after the final round.
4. **Verdict has no independent verification** — Pure text synthesis LLM call. Picks sides based on rhetoric, not evidence.
5. **Wasted tool calls** — News analyst spent 9/12 calls on filesystem ops (grep, ls, glob, read_file) that found nothing. Financial analyst called `get_company_overview(AAPL)` 8 times.
6. **Circular validation** — Both debater and researchers use the same Alpha Vantage APIs. If the source data is wrong, the debate is meaningless.

## Architecture

### Outer Layer: Debate StateGraph (Enforces Protocol)

```
main_agent_node → debater_node → main_agent_node → debater_node → ... → verdict_node
```

- **Symmetric:** Main agent always responds before verdict (defense gets last word).
- **Round definition:** 1 round = 1 main_agent + 1 debater pair.
- **`max_rounds=2`:** 2 full debate-rebuttal cycles before verdict.
- **Termination:** Debater outputs `"NO FURTHER CONCERNS"` or max rounds reached → verdict.

### Inner Layer: Main Agent (Research + Rebuttal)

```python
main_agent = create_deep_agent(
    model=self.llm,
    subagents=[
        {"name": "technical_analyst", ...},
        {"name": "news_analyst", ...},
        {"name": "financial_analyst", ...},
    ],
    system_prompt="You are an investment research coordinator...",
    name="research-orchestrator",
)
```

- Uses `task()` tool to delegate to specialist sub-agents.
- Receives concise results back (context quarantine).
- Reasons about results to form thesis (first call) or rebuttal (subsequent calls).
- Same agent for research and rebuttal — only the prompt changes.

### Debater: Independent Sources

The debater uses **independent data sources** (not the same APIs as researchers) for genuine cross-verification:

```python
{
    "name": "debater",
    "description": "Contrarian analyst who challenges investment theses using independent data sources",
    "tools": [fetch_yfinance_news, search_web_exa],
    "system_prompt": "You are a contrarian debater...",
}
```

## New Tools

### `fetch_yfinance_news(symbol, query?)`

- **Source:** Yahoo Finance (`yfinance` library, already a dependency)
- **Returns:** JSON with recent news headlines + key financial stats (P/E, EPS, 52W range, market cap, revenue/earnings growth)
- **Cost:** Free, no API key
- **Purpose:** Independent verification of financial claims

### `search_web_exa(query)`

- **Source:** Exa web search API
- **Returns:** Structured web search results (titles, URLs, content snippets)
- **Cost:** Exa API key required
- **Purpose:** Broader context — lawsuits, regulatory actions, competitive threats, analyst reports

## Structured Output

### Debater Output

```json
{
  "concerns": [
    {
      "id": "C1",
      "claim": "Original claim from thesis",
      "category": "technical|financial|news|valuation",
      "challenge": "Why this claim is wrong or incomplete",
      "severity": "CRITICAL|MAJOR|MINOR",
      "evidence": "Data from independent source supporting the challenge"
    }
  ]
}
```

### Main Agent Rebuttal Output

```json
{
  "rebuttals": [
    {
      "concern_id": "C1",
      "status": "REFUTED|PARTIALLY_VALID|CONCEDED",
      "defense": "Why the concern is wrong or how it's addressed",
      "evidence": "Data from sub-agent supporting the defense"
    }
  ]
}
```

### Verdict Input (Injected via `<system-reminder>`)

After the final debate+rebuttal cycle, the outer graph merges concerns and rebuttals by ID and injects them into the verdict prompt:

```xml
<system-reminder>
{
  "verified_facts": [
    {
      "id": "C1",
      "claim": "Fibonacci breakout above golden zone at $264.44",
      "category": "technical",
      "debater": {
        "severity": "MAJOR",
        "challenge": "$264.58 < $280.64 — pullback, not breakout",
        "evidence": "52W high $288.35, recent high $280.64, current $264.58"
      },
      "defense": {
        "status": "REFUTED",
        "rebuttal": "Golden zone derived from 52W range, price validates breakout",
        "evidence": "0.618 * (288.35 - 168.48) + 168.48 = 242.58"
      }
    }
  ]
}
</system-reminder>
```

## Tool Filtering

### Removed from All Sub-Agents

- `write_file`, `edit_file`, `ls`, `glob`, `grep` (filesystem write/edit/list/search tools — removed as they caused wasted calls)
- `read_file` remains available for controlled SKILL.md access via deepagents `FilesystemBackend(virtual_mode=True)`

### Sub-Agent Tool Assignments

| Sub-Agent | Tools | Source |
|---|---|---|
| **technical_analyst** | `fibonacci_analysis_tool`, `stochastic_analysis_tool`, `get_historical_prices` | Alpha Vantage / Alpaca |
| **news_analyst** | `get_news_sentiment`, `get_market_movers` | Alpha Vantage |
| **financial_analyst** | `get_company_overview`, `get_financial_statements`, `get_company_earnings`, `get_insider_activity`, `get_etf_holdings`, `search_ticker`, `list_insight_categories`, `get_insight_category`, `get_insight_metric` | Alpha Vantage + Insights |
| **debater** | `fetch_yfinance_news`, `search_web_exa` | Yahoo Finance + Exa (independent) |

## Event Emission

Same event types as current system. Emission points:

| Event | Emission Point |
|---|---|
| `deep_start` | Start of `analyze()` — unchanged |
| `deep_subagent_start/result` | Main agent node — captured via `lc_agent_name` metadata from `task` tool streaming |
| `deep_tool_start/end` | Inside sub-agents — captured via `AsyncCallbackHandler` on config |
| `deep_debate_start/round` | Debater node — emitted explicitly by outer graph |
| `deep_rebuttal_start/result` | Main agent node (2nd+ invocation) — emitted explicitly by outer graph |
| `deep_verdict` | Verdict node — unchanged |

## Files to Change

| File | Change |
|---|---|
| `deep_react_agent.py` | Rewrite `_build_workflow()` — new node structure, `create_deep_agent` for main agent |
| `subagent_invoker.py` | Simplify — may reduce to debater-only invocation |
| `subagents/*.py` | Convert to `SubAgent` dicts for `create_deep_agent(subagents=...)` |
| `tools/categorization.py` | Update — remove filesystem tools, add debater-specific independent tools |
| `tools/yfinance_news.py` | **New** — `fetch_yfinance_news` tool |
| `tools/exa_search.py` | **New** — `search_web_exa` tool |
| `skills/debater/*.md` | Update — reference new tools, structured output format |
| Frontend event handling | Minimal change — same event types, slightly different emission points |

## Design Decisions

1. **Outer graph for debate, inner agent for research:** The debate protocol (symmetric rounds, termination) is too important to leave to LLM discretion. The research delegation (which sub-agents to call, when) benefits from LLM reasoning.
2. **Independent sources for debater:** Prevents circular validation. The debater can't be fooled by the same API returning the same wrong data.
3. **Structured JSON throughout:** Debater and defender use the same JSON schema. The verdict receives pre-digested evidence in `<system-reminder>` tags, not raw debate text.
4. **yfinance + Exa:** yfinance provides independent financial data (free, no key). Exa provides broad web search for non-financial context (lawsuits, regulation).
5. **No filesystem tools:** Sub-agents wasted significant time on filesystem operations that returned nothing. Explicitly excluded.
