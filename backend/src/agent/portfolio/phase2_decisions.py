"""
Phase 2: Decisions - Portfolio-wide trading decisions.

This module makes holistic trading decisions after all symbol research completes.
"""

from typing import TYPE_CHECKING, Any

import structlog

from ...models.chat import ChatCreate
from ...models.message import MessageCreate, MessageMetadata
from ...models.trading_decision import SymbolAnalysisResult

if TYPE_CHECKING:
    from ...models.trading_decision import PortfolioDecisionList

from src.core.utils.date_utils import utcnow

logger = structlog.get_logger()


class Phase2DecisionsMixin:
    """Mixin providing Phase 2 decision-making capabilities."""

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
        positions_table = "| Symbol | Shares | Market Value | P/L % |\n"
        positions_table += "|--------|--------|--------------|-------|\n"
        if positions:
            for pos in positions:
                positions_table += f"| {pos['symbol']} | {pos['quantity']} | ${pos['market_value']:,.2f} | {pos['unrealized_pl_percent']:.2f}% |\n"
        else:
            positions_table += "| (No positions) | - | - | - |\n"

        # Format all symbol analyses
        analyses_section = ""
        for result in symbol_analyses:
            analyses_section += (
                f"\n### {result.symbol} ({result.analysis_type.title()})\n"
            )
            analyses_section += f"{result.analysis_text}\n"
            analyses_section += "---\n"

        # 当前美股交易时段 — 非 regular 时给 LLM 加风险提示，不阻断决策
        from datetime import UTC, datetime as _dt

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
                f"当前为 **{_label}** 时段。下列研究中的最新价可能来自延长交易时段的成交，"
                "流动性较薄，价差较大，开盘后可能出现明显跳空。请在做决策时考虑：\n"
                "- 是否将下单时间延后至开盘后再确认价格行为；\n"
                "- 若仍要使用延长时段价格作为锚点，是否需要将 entry 略微调整以预留跳空空间；\n"
                "- stop_loss / take_profit 的风险距离是否仍然合理。\n"
                "本提示不强制阻断决策，仅作为风险提醒。\n"
            )

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
  - BUY: BELOW entry_price, just under the next major support / swing low
  - SELL: ABOVE entry_price, just above the nearest resistance / swing high
- **take_profit**: where you'd close the trade in profit
  - BUY: ABOVE entry_price, at a fib extension (1.272, 1.618) or prior high
  - SELL: BELOW entry_price, at a fib retracement (0.382, 0.236) or
    next-down support

**Important — SELL semantics when closing an existing long position:**
When the SELL is to exit a holding the user already owns (the common case
in this portfolio flow, NOT opening a short), the three prices mean:
  - `entry_price` = the limit price to PLACE THE SELL ORDER AT (e.g. $645)
  - `stop_loss` = if price moves AGAINST your sell thesis (i.e. UP past
    this level), the trend hasn't reversed yet → CANCEL the sell order,
    don't dump at a worse price. NOT a literal "buy back at a loss" stop.
  - `take_profit` = if your sell order doesn't fill and price falls all
    the way down to this level, this is the LAST-RESORT exit price; you
    should have already sold by now, but at minimum sell here.
In your `reasoning_summary` for a SELL, you MUST explicitly state which
of these two interpretations applies (closing a long vs. opening a
short). Example for closing a long: "Sell limit $645 at resistance
$651.74. Cancel-above $655 if breakout confirms uptrend continuation.
Last-resort exit at $576 fib 0.382 support if the sell limit doesn't
fill."

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
