"""
Phase 2: Decisions - Portfolio-wide trading decisions.

This module makes holistic trading decisions after all symbol research completes.
"""

from typing import TYPE_CHECKING, Any

import structlog

from src.agent.portfolio.risk_calculator import (
    compute_portfolio_risk,
    render_risk_block_for_prompt,
)
from src.core.utils.date_utils import utcnow

from ...models.chat import ChatCreate
from ...models.message import MessageCreate, MessageMetadata
from ...models.trading_decision import SymbolAnalysisResult

if TYPE_CHECKING:
    from ...models.trading_decision import PortfolioDecisionList


logger = structlog.get_logger()


class Phase2DecisionsMixin:
    """Mixin providing Phase 2 decision-making capabilities."""

    async def _fetch_symbol_meta_for_risk(self, symbol: str) -> dict[str, Any]:
        """W2.6 yfinance-backed sector + beta lookup. Best-effort: any
        exception or sparse `info` dict yields {} so risk_calculator can
        flag the symbol for assumed-beta / Unknown sector. Runs sync
        yfinance in a thread to keep the async loop free."""
        import asyncio

        def _sync() -> dict[str, Any]:
            try:
                import yfinance as yf

                info = yf.Ticker(symbol).info or {}
            except Exception as e:
                logger.warning("risk_meta_yf_fetch_failed", symbol=symbol, error=str(e))
                return {}
            if not info or len(info) <= 3:
                return {}
            return {
                "sector": info.get("sector"),
                "beta": info.get("beta"),
            }

        return await asyncio.to_thread(_sync)

    async def _fetch_symbol_returns_for_risk(self, symbol: str) -> list[float]:
        """W2.6 60d daily-return series via yfinance.Ticker.history. Used
        by risk_calculator for the correlation matrix and portfolio σ."""
        import asyncio

        def _sync() -> list[float]:
            try:
                import yfinance as yf

                hist = yf.Ticker(symbol).history(period="3mo", interval="1d")
            except Exception as e:
                logger.warning(
                    "risk_returns_yf_fetch_failed", symbol=symbol, error=str(e)
                )
                return []
            if hist is None or hist.empty or "Close" not in hist:
                return []
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                return []
            returns = closes.pct_change().dropna().tolist()
            return [float(r) for r in returns][-60:]

        return await asyncio.to_thread(_sync)

    async def _make_portfolio_decisions(
        self,
        symbol_analyses: list[SymbolAnalysisResult],
        portfolio_context: dict[str, Any],
        user_id: str,
    ) -> "PortfolioDecisionList | None":
        """
        Phase 2: Make all trading decisions in a single holistic call.

        After all symbol research completes, the Portfolio Agent reviews
        everything together and makes decisions for all symbols at once.

        Args:
            symbol_analyses: List of SymbolAnalysisResult from Phase 1
            portfolio_context: Portfolio state (equity, buying_power, positions)
            user_id: User ID for tracking

        Returns:
            PortfolioDecisionList with decisions and portfolio_assessment, or None on failure
        """
        if not symbol_analyses:
            logger.info("No symbol analyses to process for decisions")
            return None

        logger.info(
            "Phase 2: Making portfolio decisions",
            symbols_count=len(symbol_analyses),
            user_id=user_id,
        )

        # Build portfolio state summary
        total_equity = portfolio_context.get("total_equity", 0)
        buying_power = portfolio_context.get("buying_power", 0)
        cash = portfolio_context.get("cash", 0)
        positions = portfolio_context.get("positions", [])

        # Format positions table
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

        # Format all symbol analyses
        analyses_section = ""
        for result in symbol_analyses:
            analyses_section += (
                f"\n### {result.symbol} ({result.analysis_type.title()})\n"
            )
            analyses_section += f"{result.analysis_text}\n"
            analyses_section += "---\n"

        # 当前美股交易时段 — 非 regular 时给 LLM 加风险提示，不阻断决策
        from datetime import UTC
        from datetime import datetime as _dt

        import pandas as _pd

        from ...services.market_data import get_market_session

        _now_utc = _pd.Timestamp(_dt.now(UTC))
        current_session = get_market_session(_now_utc)
        if current_session == "regular":
            session_stanza = ""
        else:
            _label = {
                "pre": "盘前 (pre-market)",
                "post": "盘后 (after-hours)",
                "closed": "休市 (closed)",
            }[current_session]
            session_stanza = (
                "\n## 市场时段提示 (Market Session Notice)\n\n"
                f"当前为 **{_label}** 时段。下列研究中的最新价、上方持仓表中"
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

        # W2.6: deterministic portfolio risk block (sector / beta /
        # cash% / HHI / 60d corr / σ). Render as a hard-numbers
        # constraint block injected before the symbol research, so the
        # LLM reasons against the math instead of estimating it.
        # Best-effort: any total failure produces an empty block; the
        # rest of the prompt still works.
        try:
            # Adapt context['positions'] (dict) to the duck-typed
            # interface risk_calculator wants. Use a lightweight wrapper
            # rather than a full Holding rehydrate to keep this cheap.
            class _PosAdapter:
                def __init__(self, p: dict[str, Any]):
                    self.symbol = p["symbol"]
                    self.quantity = int(p.get("quantity") or 0)
                    self.market_value = float(p.get("market_value") or 0.0)
                    self.current_price = (
                        self.market_value / self.quantity if self.quantity > 0 else 0.0
                    )

            adapted = [_PosAdapter(p) for p in positions] if positions else []
            risk = await compute_portfolio_risk(
                holdings=adapted,
                cash=float(cash or 0.0),
                fetch_meta=self._fetch_symbol_meta_for_risk,
                fetch_returns=self._fetch_symbol_returns_for_risk,
            )
            risk_block = render_risk_block_for_prompt(risk)
        except Exception as e:
            logger.warning("phase2_risk_block_failed", error=str(e))
            risk_block = ""

        # Build the holistic decision prompt
        decision_prompt = f"""# Portfolio Trading Decisions

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
"""

        try:
            # Import the schema here to avoid circular imports
            from ...models.trading_decision import PortfolioDecisionList

            # Single structured call for all decisions
            decision_result = await self.react_agent.ainvoke_structured(
                prompt=decision_prompt,
                schema=PortfolioDecisionList,
                context=None,  # Context is embedded in prompt
            )

            logger.info(
                "Phase 2: Portfolio decisions completed",
                decisions_count=len(decision_result.decisions),
                assessment_preview=decision_result.portfolio_assessment[:100],
            )

            return decision_result  # Return full PortfolioDecisionList

        except Exception as e:
            logger.error(
                "Phase 2: Failed to make portfolio decisions",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            # Return None on failure - no orders will be executed
            return None

    async def _get_portfolio_decisions_chat_id(self) -> str:
        """
        Get or create the "Portfolio Decisions" chat for Phase 2 decision messages.

        Unlike symbol-specific chats, this is a single chat that aggregates all
        portfolio-level trading decisions made by the agent.

        Returns:
            Chat ID for "Portfolio Decisions" chat
        """
        owner_id = "portfolio_agent"
        chat_title = "Portfolio Decisions"

        # Try to find existing Portfolio Decisions chat
        chats = await self.chat_repo.list_by_user(owner_id)
        for chat in chats:
            if chat.title == chat_title:
                logger.info(
                    "Found existing Portfolio Decisions chat",
                    owner=owner_id,
                    chat_id=chat.chat_id,
                )
                return chat.chat_id

        # Create new Portfolio Decisions chat
        chat_create = ChatCreate(
            title=chat_title,
            user_id=owner_id,
        )
        chat = await self.chat_repo.create(chat_create)
        logger.info(
            "Created new Portfolio Decisions chat",
            owner=owner_id,
            chat_id=chat.chat_id,
        )
        return chat.chat_id

    async def _store_portfolio_decision_message(
        self,
        decision_result: "PortfolioDecisionList",
        symbol_analyses: list[SymbolAnalysisResult],
        portfolio_context: dict[str, Any],
        flow: str | None = None,
    ) -> None:
        """
        Store Phase 2 portfolio decision as a chat message for history viewing.

        This creates a formatted markdown message with all trading decisions and
        the portfolio assessment, stored with analysis_type="portfolio" for filtering.

        Args:
            decision_result: PortfolioDecisionList from Phase 2
            symbol_analyses: List of Phase 1 symbol analyses
            portfolio_context: Portfolio state (equity, buying_power, positions)
        """

        try:
            # Get the Portfolio Decisions chat
            chat_id = await self._get_portfolio_decisions_chat_id()

            # Build analysis ID for this portfolio decision batch
            timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
            symbols_str = "_".join(sorted([a.symbol for a in symbol_analyses[:3]]))
            if len(symbol_analyses) > 3:
                symbols_str += f"_+{len(symbol_analyses) - 3}more"
            analysis_id = f"portfolio_{symbols_str}_{timestamp}"

            # Format the message content as markdown
            message_content = "## 📊 Portfolio Trading Decisions\n\n"
            message_content += f"**Date:** {utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            message_content += f"**Symbols Analyzed:** {len(symbol_analyses)}\n"
            message_content += (
                f"**Decisions Made:** {len(decision_result.decisions)}\n\n"
            )

            # Portfolio assessment
            message_content += "### Portfolio Assessment\n\n"
            message_content += f"{decision_result.portfolio_assessment}\n\n"

            # Individual decisions: a compact at-a-glance table (no reasoning
            # column — long sentences blow up table columns and force a
            # horizontal scroll), followed by per-decision reasoning blocks
            # so each rationale gets its own readable paragraph.
            message_content += "### Trading Decisions\n\n"
            message_content += (
                "| Symbol | Decision | Size % | Entry | Stop | Target | Confidence |\n"
            )
            message_content += (
                "|--------|----------|--------|-------|------|--------|------------|\n"
            )

            for decision in decision_result.decisions:
                size_str = (
                    f"{decision.position_size_percent}%"
                    if decision.position_size_percent
                    else "-"
                )
                entry_str = (
                    f"${decision.entry_price:.2f}"
                    if decision.entry_price is not None
                    else "—"
                )
                stop_str = (
                    f"${decision.stop_loss:.2f}"
                    if decision.stop_loss is not None
                    else "—"
                )
                target_str = (
                    f"${decision.take_profit:.2f}"
                    if decision.take_profit is not None
                    else "—"
                )
                message_content += (
                    f"| {decision.symbol} | {decision.decision.value} | "
                    f"{size_str} | {entry_str} | {stop_str} | {target_str} | "
                    f"{decision.confidence}/10 |\n"
                )

            message_content += "\n#### Reasoning\n\n"
            for decision in decision_result.decisions:
                # Full reasoning — no truncation. Each decision gets its own
                # block so long paragraphs don't crowd the table.
                message_content += (
                    f"**{decision.symbol} ({decision.decision.value})** — "
                    f"{decision.reasoning_summary}\n\n"
                )

            # Create metadata for filtering
            analyzed_symbols = [a.symbol for a in symbol_analyses]
            raw_data: dict[str, Any] = {
                "decisions_count": len(decision_result.decisions),
                "symbols_analyzed": analyzed_symbols,
                "total_equity": portfolio_context.get("total_equity", 0),
                "buying_power": portfolio_context.get("buying_power", 0),
            }
            if flow:
                # Used by GET /api/portfolio/chat-history to label cards as
                # 持仓分析 (holdings) / 今日推荐 (picks). Single-symbol Phase 2
                # runs have no flow tag and fall through to 个股分析.
                raw_data["flow"] = flow
            metadata = MessageMetadata(
                symbol=None,  # Portfolio-level, not symbol-specific
                analysis_id=analysis_id,
                analysis_type="portfolio",  # Phase 2 = portfolio decision
                raw_data=raw_data,
            )

            # W1.11: append AI-generated disclaimer footer to every persisted
            # decision message so the human reader sees it at the bottom of
            # the chat modal even if the rest of the report is short.
            message_content += (
                "\n\n---\n_🤖 AI-generated · Not investment advice. "
                "Verify all data and consult a licensed advisor before "
                "executing any trade._\n"
            )

            # Create and store the message
            message_create = MessageCreate(
                chat_id=chat_id,
                role="assistant",
                content=message_content,
                source="llm",
                metadata=metadata,
            )
            message = await self.message_repo.create(message_create)

            logger.info(
                "Phase 2: Portfolio decision message stored",
                chat_id=chat_id,
                message_id=message.message_id,
                analysis_id=analysis_id,
                decisions_count=len(decision_result.decisions),
            )

        except Exception as e:
            logger.error(
                "Failed to store portfolio decision message",
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            # Don't raise - decision was made even if storage failed

    async def _run_phase2_decisions(
        self,
        all_analysis_results: list[SymbolAnalysisResult],
        portfolio_context: dict[str, Any],
        user_id: str,
        dry_run: bool,
        flow: str | None = None,
    ) -> tuple[Any, list[Any]]:
        """
        Run Phase 2: Make portfolio-wide trading decisions.

        Args:
            all_analysis_results: Symbol analyses from Phase 1
            portfolio_context: Portfolio state
            user_id: User ID for tracking
            dry_run: If True, skip decision making

        Returns:
            Tuple of (decision_result, trading_decisions)
        """
        if dry_run:
            return None, []

        if not all_analysis_results:
            await self._store_phase2_failure_message(
                reason="No symbol analyses available. Phase 1 may have failed completely.",
            )
            return None, []

        if not portfolio_context:
            await self._store_phase2_failure_message(
                reason="Portfolio context unavailable. Failed to retrieve account information from Alpaca.",
            )
            return None, []

        logger.info(
            "Phase 2: Portfolio Agent making holistic decisions",
            symbols_count=len(all_analysis_results),
        )

        # Get decisions from Portfolio Agent (returns PortfolioDecisionList)
        decision_result = await self._make_portfolio_decisions(
            symbol_analyses=all_analysis_results,
            portfolio_context=portfolio_context,
            user_id=user_id,
        )

        # Extract trading decisions for Phase 3
        trading_decisions = decision_result.decisions if decision_result else []

        # Store Phase 2 portfolio decision as a chat message for history
        if decision_result:
            await self._store_portfolio_decision_message(
                decision_result=decision_result,
                symbol_analyses=all_analysis_results,
                portfolio_context=portfolio_context,
                flow=flow,
            )

        return decision_result, trading_decisions

    async def _store_phase2_failure_message(
        self,
        reason: str,
        success_rate: float | None = None,
        successful_count: int | None = None,
        total_count: int | None = None,
    ) -> None:
        """
        Store a failure message when Phase 2 is skipped.

        This creates a visible record in the Portfolio Decisions chat so users
        can see why no trading decisions were made.

        Args:
            reason: Why Phase 2 was skipped
            success_rate: Phase 1 success rate (if applicable)
            successful_count: Number of successful analyses
            total_count: Total symbols attempted
        """
        try:
            chat_id = await self._get_portfolio_decisions_chat_id()

            timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
            analysis_id = f"portfolio_failed_{timestamp}"

            # Format failure message
            message_content = "## ⚠️ Portfolio Analysis Failed\n\n"
            message_content += f"**Date:** {utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            message_content += "**Status:** Phase 2 Skipped\n\n"
            message_content += f"### Reason\n\n{reason}\n\n"

            if success_rate is not None:
                message_content += "### Details\n\n"
                message_content += f"- Success Rate: {success_rate:.1%}\n"
                message_content += f"- Successful Analyses: {successful_count}\n"
                message_content += f"- Total Symbols: {total_count}\n"

            metadata = MessageMetadata(
                symbol=None,
                analysis_id=analysis_id,
                analysis_type="portfolio",
                raw_data={
                    "status": "failed",
                    "reason": reason,
                    "success_rate": success_rate,
                },
            )

            message_create = MessageCreate(
                chat_id=chat_id,
                role="assistant",
                content=message_content,
                source="system",
                metadata=metadata,
            )
            await self.message_repo.create(message_create)

            logger.info(
                "Phase 2 failure message stored",
                chat_id=chat_id,
                reason=reason,
            )

        except Exception as e:
            logger.error(
                "Failed to store Phase 2 failure message",
                error=str(e),
            )
