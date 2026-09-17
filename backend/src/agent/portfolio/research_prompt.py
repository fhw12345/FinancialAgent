"""Existing Phase 1 research instructions, extracted without changing their text."""


def render_research_prompt(symbol: str, language_directive: str) -> str:
    from ...services.evidence.context import reminder

    evidence = reminder(symbol)
    return f"""# Symbol Research: {symbol}

**FIRST ACTION REQUIRED**: Call `get_stock_quote` with symbol="{symbol}" and
`get_company_overview` with symbol="{symbol}" IMMEDIATELY as your opening
tool calls. Do not write any introduction. Do not list your capabilities.
Use the tools NOW.

After you have the basic data, use additional tools (fibonacci_analysis_tool,
get_news_sentiment, get_momentum_indicator, get_financial_statements, etc.)
to satisfy the research below.

## Research Requirements

1. **Technical Analysis**
   - Fibonacci retracement levels and trend analysis
   - Support and resistance levels
   - Momentum indicators (RSI, MACD, Stochastic)
   - Recent price action and volume patterns

2. **Fundamental Analysis**
   - Company overview and business model
   - Financial health (revenue, earnings, cash flow)
   - News sentiment and recent developments
   - Industry trends and competitive position

3. **Value Assessment**
   - Current valuation metrics (P/E, P/B, etc.)
   - Growth prospects and catalysts
   - Risk factors and concerns
   - Short-term vs long-term outlook

**IMPORTANT**: Provide factual research and analysis only.
Do NOT make buy/sell/hold recommendations - decisions will be made separately
by the Portfolio Agent after reviewing all symbol analyses together.

**EXTENDED-HOURS RULE (W3.18)**: When a quote tool emits an
"After-hours: $X" or "Pre-market: $X" companion line below the primary
print, treat that companion as the most recent market signal — note it
verbatim in your report (with its source-ID token) whenever the move is
≥ ±1% versus the primary, since that magnitude routinely changes the
short-term thesis (overnight gap, earnings reaction, news leak).

**FIBONACCI SANITY RULE (W1.9)**: When the fibonacci_analysis_tool output
contains `range_position: above_range` or `range_position: below_range`
(price has broken out of the swing structure), the levels are STALE.
DO NOT cite the golden zone or any fib retracement number as
support/resistance. Instead, either re-call the tool with a wider
date window, or note in the report that no valid fib structure
applies and switch to other technical references (moving averages,
prior swing highs/lows, volume profile).

**FUNDAMENTAL DATA RULE (W1.5-W1.8)**: When a tool returns the literal
phrase "unsubstantiated" (the unavailable_message format), the
underlying data could not be fetched from any source. DO NOT make
valuation claims (P/E vs peers, "cheap", "expensive", "undervalued")
that depend on that field. State explicitly that the data is
unavailable and proceed without that line of argument.

**INSIDER FRAMING RULE (W3.11)**: Insider sells are NOT automatically
bearish. Only frame insider activity as bearish when ALL THREE of the
following hold:

1. **Cluster size** — at least 3 separate sell transactions inside a
   single 30-day window. A single sell, however large, does not
   establish a cluster.
2. **Material size** — at least one transaction in the cluster has
   `pct_of_holdings_after` > 0.05 (the insider sold > 5% of their
   remaining position). Sells under that threshold are routine
   liquidity / tax events.
3. **Breaks the 12-month pattern** — the cluster is inconsistent with
   the symbol's last_12mo summary (e.g. the prior 11 months were
   quiet, or were dominated by 10b5-1 sells, and the cluster is the
   first burst of discretionary activity).

PLAN-TYPE OVERRIDE: If a transaction's `plan_type` is `10b5-1`, it
MUST NOT be cited as discretionary bearish — these are pre-announced
mechanical sales scheduled before the trader had material non-public
information. State the plan_type and the plan_adopted_date when
present, and treat the transaction as neutral. `discretionary` and
`unknown` plan types may contribute to the bearish framing only when
the three conditions above also hold. When `plan_type` is missing
entirely (the SEC fetch failed for this symbol), default to neutral
framing rather than inferring discretionary.

**TOKEN PRESERVATION RULE (W3.16)**: Tool outputs end with a
provenance line shaped exactly like:

    Source: finnhub [FH-Q-NVDA-2026-05-09] asof 2026-05-09T14:30Z

The bracketed token (e.g. `[FH-Q-NVDA-2026-05-09]`, `[AV-OV-NVDA-...]`,
`[FH-N-NVDA-...]`, `[FH-INS-NVDA-...]`) is contract metadata, not
prose. You MUST:

1. Preserve every such token verbatim — do not rewrite, translate,
   abbreviate, or strip the brackets / hyphens / dates.
2. When a sentence in your final research report cites a specific
   number, headline, or insider transaction that came from a tool,
   append the matching `[ID]` token at the end of that sentence (or
   bullet). One token per sentence is enough; do not duplicate the
   same token across consecutive bullets that already share an ID.
3. If a fact came from multiple tools (e.g. price from quote +
   market-cap from overview), append both tokens space-separated.
4. Do NOT invent token strings. If a claim has no backing tool call,
   state it without a token rather than fabricating one.
5. Never delete a `Source:` line you observed in a tool result while
   summarizing — Phase 2 (the Portfolio Agent that reads your report)
   relies on these tokens to build the thesis citations W3.6 requires.

{language_directive}
{evidence}
"""
