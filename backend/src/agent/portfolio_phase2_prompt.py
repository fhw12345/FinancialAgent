"""Canonical renderer for the registered Portfolio Phase 2 prompt."""

from typing import Any

from pydantic import PrivateAttr

from src.core.localization import ANALYSIS_OUTPUT_LANG
from src.models.trading_decision import PortfolioDecisionList


class GovernedPortfolioDecisionList(PortfolioDecisionList):
    _prompt_versions: dict[str, str] = PrivateAttr(default_factory=dict)

    @property
    def prompt_versions(self) -> dict[str, str]:
        return dict(self._prompt_versions)

    def record_prompt_version(self, prompt_id: str, version: str) -> None:
        self._prompt_versions[prompt_id] = version


def _phase2_language_directive() -> str:
    if ANALYSIS_OUTPUT_LANG != "en":
        raise RuntimeError(
            f"Phase 2 prompt only supports English output; "
            f"ANALYSIS_OUTPUT_LANG={ANALYSIS_OUTPUT_LANG!r}"
        )
    return (
        "LANGUAGE REQUIREMENT: Respond in English.\n"
        "Keep ticker symbols, numbers, currency amounts, percentages, "
        "source-ID tokens (e.g. [FH-Q-AAPL-2026-05-09]), and ISO "
        "timestamps verbatim. The frontend translates display strings on "
        "the persistence boundary; this prompt does not need to add "
        "translations inline."
    )


_PHASE2_LANGUAGE_DIRECTIVE = _phase2_language_directive()


def _format_positions_table(positions: list[dict[str, Any]]) -> str:
    positions_table = "| Symbol | Shares | Market Value | P/L % | Session |\n"
    positions_table += "|--------|--------|--------------|-------|---------|\n"
    if positions:
        for pos in positions:
            sess = pos.get("session") or "—"
            sess_label = f"**{sess}** ⚠️" if sess in ("pre", "post") else sess
            positions_table += (
                f"| {pos['symbol']} | {pos['quantity']} | "
                f"${pos['market_value']:,.2f} | "
                f"{pos['unrealized_pl_percent']:.2f}% | {sess_label} |\n"
            )
    else:
        positions_table += "| (No positions) | - | - | - | - |\n"
    return positions_table


def _format_analyses(symbol_analyses: list[Any]) -> str:
    analyses_section = ""
    for result in symbol_analyses:
        analyses_section += f"\n### {result.symbol} ({result.analysis_type.title()})\n"
        analyses_section += f"{result.analysis_text}\n"
        analyses_section += "---\n"
    return analyses_section


def _render_session_stanza(current_session: str) -> str:
    if current_session == "regular":
        return ""

    label = {
        "pre": "盘前 (pre-market)",
        "post": "盘后 (after-hours)",
        "closed": "休市 (closed)",
    }[current_session]
    return (
        "\n## 市场时段提示 (Market Session Notice)\n\n"
        f"当前为 **{label}** 时段。下列研究中的最新价、上方持仓表中"
        "标注 `pre` / `post` 的 Market Value、以及 quote 工具返回的 "
        "`Session: pre/post` 价格，都来自延长交易时段的成交。延长时段 "
        "**流动性 < 5% RTH**，价差较大，单笔大单即可显著推动价格，"
        "开盘后可能出现明显跳空。请在做决策时考虑：\n"
        "- entry_price 应预留跳空缓冲，不要紧贴当前盘前/盘后价；\n"
        "- stop_loss 不要锚定在盘前/盘后形成的低点上 —— 那些低点流动性"
        "极差，开盘后大概率被穿；优先用 RTH 收盘 / RTH 形成的支撑位；\n"
        "- take_profit 同理：盘前/盘后高点不是真实阻力，请用 RTH 价格"
        "结构上的阻力 / fib 1.272 / 1.618;\n"
        "- 若行情极端 (盘前 ±5% 以上)，倾向 HOLD 等开盘后再确认，"
        "而不是在延长时段下决策。\n"
        "本提示不强制阻断决策，仅作为风险提醒。\n"
    )


def render_portfolio_phase2_prompt(
    *,
    symbol_analyses: list[Any],
    total_equity: float,
    buying_power: float,
    cash: float,
    positions: list[dict[str, Any]],
    risk_block: str,
    current_session: str,
) -> str:
    """Render the complete portfolio decision prompt."""
    positions_table = _format_positions_table(positions)
    analyses_section = _format_analyses(symbol_analyses)
    session_stanza = _render_session_stanza(current_session)

    return f"""# Portfolio Trading Decisions

You are a Portfolio Manager. Review ALL the symbol research below and make trading decisions
considering the overall portfolio optimization, diversification, and risk management.

## Current Portfolio State

**Account Summary:**
- Total Equity: ${total_equity:,.2f}
- Buying Power: ${buying_power:,.2f}
- Cash: ${cash:,.2f}

**Current Holdings:**
{positions_table}
{risk_block}
{session_stanza}
## Symbol Research Results
{analyses_section}

## Decision Rules

For EACH analyzed symbol, decide ONE action:

- **BUY**: Add new position or increase existing
  - position_size_percent = % of BUYING POWER to spend
  - Example: 10% means spend 10% of ${buying_power:,.2f} = ${buying_power * 0.1:,.2f}

- **SELL**: Reduce or exit position (MUST be a current holding)
  - position_size_percent = % of CURRENT HOLDING to sell
  - Example: 50% of 100 shares = sell 50 shares
  - SELLs execute FIRST to gain liquidity for BUYs

- **HOLD**: No action needed
  - position_size_percent should be null
  - entry_price / stop_loss / take_profit MUST be null

## Price Levels (REQUIRED for BUY/SELL)

For every BUY or SELL decision you MUST set three concrete prices, each
ANCHORED to a specific level that appeared in the symbol's research above
(fibonacci retracement/extension, support/resistance, swing high/low,
pressure zone). DO NOT make prices up — every number must be traceable to
a tool output.

- **entry_price**: limit-order price to enter the position
  - BUY: a price near current market that aligns with a support / fib
    retracement (e.g. 0.382, 0.5, 0.618) / pressure zone
  - SELL: a price near current market at a resistance / fib level / prior
    swing high
- **stop_loss**: where you'd cut the trade if it goes against you
  - LONG-SIDE intents (BUY = open_long, SELL = close_long the
    common case): stop_loss MUST be BELOW entry_price. For BUY, this
    is the protective stop under the next major support / swing low.
    For SELL closing a long, this is the "if it dumps further, get
    out at any price" floor — NOT a cancel-above price.
  - SHORT-SIDE intents (open_short, close_short — rare; only when
    you actually intend a short trade): stop_loss MUST be ABOVE
    entry_price.
- **take_profit**: where you'd close the trade in profit
  - LONG-SIDE: ABOVE entry_price (fib extension 1.272/1.618 or prior
    high). For SELL closing a long, this is the runner target if
    the sell order doesn't fill and the trend keeps extending.
  - SHORT-SIDE: BELOW entry_price.

**SELL geometry hard rule (W1.1 validator will reject violations):**
A SELL with `intent` defaulting to `close_long` REQUIRES
`stop_loss < entry_price < take_profit`. If you mean a *real short
trade* (rare in this portfolio flow), set `intent: "open_short"`
explicitly and use `stop_loss > entry_price > take_profit`. The
reverse layout for a close_long will fail Pydantic validation and
the entire batch will be rejected.

In your `reasoning_summary` for a SELL, you MUST explicitly state
which intent applies (closing a long vs. opening a short). Example
for closing a long: "Sell limit $645 at resistance $651.74 (entry).
Stop $605 if support breaks (last-resort floor). Target $710 fib
1.618 if rally extends and limit doesn't fill."

The `reasoning_summary` MUST cite the specific tool-derived levels you
used for ALL THREE prices (entry/stop/take), not just two. A reasoning
that names the stop and target but leaves the entry-price anchor
unspecified is not acceptable.

## Important Considerations

1. **Liquidity First**: SELL orders execute before BUYs to free up buying power
2. **Diversification**: Avoid over-concentration in any single position
3. **Risk Management**: Consider correlation between positions
4. **Position Sizing**: Use confidence level to scale position sizes
5. **Holdings vs Watchlist**: Holdings can be SELL/HOLD; Watchlist can be BUY/HOLD
6. **Extended-Hours Companion (W3.18)**: When a Phase 1 quote tool
   reports an "After-hours: $X (±Y%)" or "Pre-market: $X (±Y%)" line
   below the primary print, that companion is the freshest signal
   available. Treat any companion move ≥ ±1% versus the primary as
   material — your `reasoning_summary` MUST name the companion price
   and direction (with its source-ID token) before recommending an
   action; ignoring an overnight ±1%+ move while citing only the stale
   regular-session close is the same provenance failure as ignoring a
   fresh news catalyst.

## Structured Research Blocks (W2.7+) — REQUIRED for BUY/SELL

Every BUY or SELL decision MUST populate ALL of the blocks below.
HOLD decisions SHOULD populate them when the evidence exists, but
may omit any block where the Phase 1 research did not produce the
underlying data. Emitting null on a BUY/SELL block because "it's
safer" is NOT acceptable — the dashboard renders these blocks, the
consistency gate scores decisions on them, and a BUY/SELL with
null research blocks is treated as a degraded decision.

If your Phase 1 research genuinely lacks the inputs for a block,
downgrade the decision to HOLD and explain in `reasoning_summary`
what data is missing — do NOT issue a BUY/SELL with empty research.

Validators will reject malformed blocks (length / probability sum /
derivation drift). Satisfy the rules:

- `thesis`: exactly 3 short bullet points (the elevator-pitch view).
  **Each bullet that names a number, ratio, growth rate, transaction,
  headline, or insider event MUST end with the matching source-ID
  token in square brackets** — the same token that appears in the
  `Source: <provider> [<ID>] asof <iso>` line at the bottom of the
  tool output that produced the fact. Examples of valid tokens:
  `[FH-Q-AAPL-2026-05-09]` (Finnhub quote), `[AV-OV-NVDA-2025-09-30]`
  (AV company overview), `[YF-CF-MSFT-2025-12-31]` (yfinance
  fallback cash flow), `[FH-N-AMZN-2026-05-08]` (Finnhub news),
  `[FH-INS-TSLA-2026-05-07]` (Finnhub insider). If the bullet is a
  pure qualitative judgement ("the cohort is rate-sensitive") with
  no specific datapoint, the citation is optional. Bullets that
  cite a number without a source-ID token are research malpractice
  — the consistency_gate will flag them and the dashboard will
  render them with a "uncited" warning chip.
- `reasoning_summary` (W3.17): the same source-ID token rule
  applies to this string field. Whenever `reasoning_summary` names
  a number, ratio, growth rate, transaction, headline, or insider
  event that you lifted from the Phase 1 research above, append
  the matching source-ID token in square brackets right after that
  number — same `[FH-Q-...]` / `[AV-OV-...]` / `[YF-CF-...]` /
  `[FH-N-...]` / `[FH-INS-...]` shapes as the thesis rule. This
  matters most for HOLD decisions: the schema lets HOLD leave
  `thesis` null and route the entire narrative into
  `reasoning_summary`, so without this rule HOLD decisions silently
  drop every citation Phase 1 worked to preserve. Pure qualitative
  phrasing ("the breakout looks tired", "wait for digestion") may
  skip the citation. A `reasoning_summary` that names concrete
  Phase 1 numbers without source-ID tokens is research malpractice
  for the same reason as an uncited thesis bullet.
- `valuation`: at least 2 ValuationMethod objects (each with method
  one of pe_vs_peer / ev_revenue / ev_ebitda / peg / dcf_quick /
  p_book / ps_ratio / other, plus value and note). Triangulating
  with a single method is rejected.
- `price_target`: value + horizon_days (7 to 730) + optional method.
- `scenarios`: bull / base / bear. Each ScenarioCase carries
  price_target, probability, rationale. The three probabilities
  MUST sum to 1.0 (within ±0.02). **Each `rationale` MUST cite a
  base rate or historical frequency** — e.g. "post-Q earnings drift
  +5% in 60% of last 8 quarters" or "SPY -20% drawdowns happen
  ~once every 4 years" — not just vibes. A scenario set with
  vibes-only rationales is research malpractice.
- `catalysts`: list of event + eta_window for the next ~4 weeks.
- `risks`: exactly 3, ranked by importance.

### Worked example (BUY decision)

```
{{
  "symbol": "EXMP",
  "decision": "BUY",
  "position_size_percent": 8,
  "entry_price": 142.50,
  "stop_loss": 134.00,
  "take_profit": 168.00,
  "confidence": 7,
  "reasoning_summary": "Buy limit $142.50 at 0.5 fib retracement support. Stop $134 below swing low (atr_stop with atr=4.2, n=2). Target $168 at 1.272 fib extension. Thesis cites datacenter capex acceleration [FH-N-EXMP-2026-02-08]; 2 valuation methods triangulate fair value $155-170 [AV-OV-EXMP-2025-12-31].",
  "thesis": [
    "Q4 datacenter capex guide raised 18% YoY, locking 2026 revenue floor [FH-N-EXMP-2026-02-08]",
    "Operating margin expansion from 28% to 33% as new fab depreciation rolls off [AV-OV-EXMP-2025-12-31]",
    "$8B buyback authorization shrinks float ~5% over next 12 months [FH-N-EXMP-2026-01-22]"
  ],
  "valuation": [
    {{"method": "pe_vs_peer", "value": 24.5, "note": "vs MAG7 median 28.1, 13% discount"}},
    {{"method": "ev_ebitda", "value": 18.2, "note": "vs sector 21.4, 15% discount"}}
  ],
  "price_target": {{"value": 168.0, "horizon_days": 365, "method": "blended"}},
  "scenarios": {{
    "bull": {{"price_target": 195, "probability": 0.25, "rationale": "datacenter capex beats by 10%+ — happened in 4 of last 10 cycles"}},
    "base": {{"price_target": 168, "probability": 0.55, "rationale": "guide-in-line outcomes occurred in ~55% of last 20 quarters across megacap semis"}},
    "bear": {{"price_target": 128, "probability": 0.20, "rationale": "macro risk-off drawdown — SPY -15%+ pullbacks happen roughly once every 18 months historically"}}
  }},
  "catalysts": [
    {{"event": "Q1 earnings", "eta_window": "2026-05-22"}},
    {{"event": "GTC keynote", "eta_window": "2026-06-10"}}
  ],
  "risks": [
    "China export-control escalation could remove ~12% of revenue",
    "Hyperscaler capex digestion if AI ROI questioned by Q2 earnings",
    "Multiple compression if 10Y yield breaks above 5%"
  ],
  "entry_derivation": {{"value": 142.50, "formula": "0.5 fib retracement of swing $120→$165", "inputs": {{"swing_low": 120, "swing_high": 165}}}},
  "stop_derivation": {{"value": 134.00, "formula": "price - n*atr", "inputs": {{"price": 142.5, "atr": 4.25, "n": 2.0}}}}
}}
```

## Numeric Derivation (W2.9)

When you set a concrete entry_price / stop_loss / take_profit,
attach a Derivation (value + formula + inputs) to the matching
`*_derivation` field. The validator requires derivation.value to
match the headline number within 0.5%, so the formula and the price
cannot drift apart silently. Two reusable helpers exist (call them
in your reasoning rather than re-deriving from scratch):

  - `atr_stop(price, atr, n=1.5, side='long')` for protective stops
  - `vol_adjusted_size(account_risk_dollar, stop_distance_dollar,
     price?)` for position sizing

If you cannot give a derivation, prefer a qualitative band ("trim
~30-50% on a rebound to $278-$282") in `reasoning_summary` over a
spuriously precise number.

Provide a decision for EVERY symbol in the research above.
Include short reasoning (1-2 sentences) for each decision.

## Language Requirement

{_PHASE2_LANGUAGE_DIRECTIVE}
"""
