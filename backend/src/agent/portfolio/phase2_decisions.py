"""Portfolio-wide Phase 2 trading decisions."""

from typing import TYPE_CHECKING, Any

import structlog

from src.agent.portfolio.risk_calculator import (
    SymbolMeta,
    compute_portfolio_risk,
    render_risk_block_for_prompt,
)
from src.agent.prompt_registry import get_prompt, render_prompt
from src.core.utils.date_utils import utcnow

from ...models.chat import ChatCreate
from ...models.message import MessageCreate, MessageMetadata
from ...models.trading_decision import SymbolAnalysisResult

if TYPE_CHECKING:
    from ...database.repositories.chat_repository import ChatRepository
    from ...database.repositories.message_repository import MessageRepository
    from ..langgraph_react_agent import FinancialAnalysisReActAgent
    from ..portfolio_phase2_prompt import GovernedPortfolioDecisionList


logger = structlog.get_logger()


class Phase2DecisionsMixin:
    """Mixin providing Phase 2 decision-making capabilities."""

    react_agent: "FinancialAnalysisReActAgent"
    chat_repo: "ChatRepository"
    message_repo: "MessageRepository"

    async def _fetch_symbol_meta_for_risk(self, symbol: str) -> SymbolMeta:
        """Fetch best-effort sector and beta metadata without blocking."""
        import asyncio

        def _sync() -> SymbolMeta:
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
        """Fetch the latest 60 daily returns without blocking."""
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
    ) -> "GovernedPortfolioDecisionList | None":
        """
        Phase 2: Make all trading decisions in a single holistic call.

        After all symbol research completes, the Portfolio Agent reviews
        everything together and makes decisions for all symbols at once.

        Args:
            symbol_analyses: List of SymbolAnalysisResult from Phase 1
            portfolio_context: Portfolio state (equity, buying_power, positions)
            user_id: User ID for tracking
        Returns the governed structured decision batch, or None on failure.
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

        from datetime import UTC
        from datetime import datetime as _dt

        import pandas as _pd

        from ...services.market_data import get_market_session

        _now_utc = _pd.Timestamp(_dt.now(UTC))
        current_session = get_market_session(_now_utc)

        # Best-effort deterministic risk constraints for the prompt.
        try:

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

        phase2_prompt = get_prompt("portfolio-phase2")
        decision_prompt = render_prompt(
            "portfolio-phase2",
            symbol_analyses=symbol_analyses,
            total_equity=total_equity,
            buying_power=buying_power,
            cash=cash,
            positions=positions,
            risk_block=risk_block,
            current_session=current_session,
        )

        try:
            from ..portfolio_phase2_prompt import GovernedPortfolioDecisionList

            raw_decision_result = await self.react_agent.ainvoke_structured(
                prompt=decision_prompt,
                schema=GovernedPortfolioDecisionList,
                context=None,  # Context is embedded in prompt
            )
            decision_result = GovernedPortfolioDecisionList.model_validate(
                raw_decision_result
            )
            decision_result.record_prompt_version(
                phase2_prompt.prompt_id,
                phase2_prompt.versioned_id,
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
        decision_result: "GovernedPortfolioDecisionList",
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
                "prompt_versions": getattr(
                    decision_result,
                    "prompt_versions",
                    {},
                ),
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
                reason="Portfolio context unavailable from local holdings.",
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
