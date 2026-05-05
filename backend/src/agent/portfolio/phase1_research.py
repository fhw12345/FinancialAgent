"""
Phase 1: Research - Independent symbol analysis.

This module handles concurrent research for individual symbols without portfolio context.
"""

import asyncio
from typing import Any

import structlog

from src.core.utils.date_utils import utcnow

from ...models.chat import ChatCreate
from ...models.message import MessageCreate, MessageMetadata
from ...models.trading_decision import SymbolAnalysisResult

logger = structlog.get_logger()


class Phase1ResearchMixin:
    """Mixin providing Phase 1 research capabilities."""

    async def _analyze_symbol(
        self,
        symbol: str,
        user_id: str,
        analysis_type: str,
        suppress_chat: bool = False,
    ) -> SymbolAnalysisResult | None:
        """
        Phase 1: Independent symbol research using ReAct agent with tools.

        Pure research without portfolio context or trading decisions.
        Decisions are made holistically in Phase 2 after all analyses complete.

        Args:
            symbol: Stock symbol to analyze
            user_id: User ID (use "portfolio_agent" for system analysis)
            analysis_type: Type of analysis (holding, watchlist)
            suppress_chat: If True, skip per-symbol chat/message creation —
                used by the dashboard two-button flows that store research
                inline on portfolio_orders.metadata.full_research instead.

        Returns:
            SymbolAnalysisResult with analysis text, or None if failed
        """
        try:
            # Generate analysis_id for tracking
            timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
            analysis_id = f"{symbol}_{analysis_type}_{timestamp}"

            logger.info(
                "Phase 1: Starting symbol research",
                symbol=symbol,
                user_id=user_id,
                analysis_type=analysis_type,
                analysis_id=analysis_id,
            )

            # Get symbol-specific chat ID for context retrieval
            # Symbol chat is only needed if we're going to write to it.
            chat_id = (
                f"ephemeral_{symbol}_{analysis_id}"
                if suppress_chat
                else await self._get_symbol_chat_id(symbol, user_id)
            )

            # Fetch historical messages for context management (sliding window + summary)
            # When suppress_chat=True we skip both the historical-context
            # lookup and the message persist (caller stores the research
            # inline elsewhere). Build a synthetic empty history.
            if suppress_chat:
                historical_messages = []
            else:
                historical_messages = await self.message_repo.get_by_chat(chat_id)

            # Pure research prompt - NO portfolio context, NO trading decisions
            # Decisions will be made in Phase 2 with full portfolio visibility
            #
            # IMPORTANT: lead with an explicit imperative "first action" line so
            # Claude does not interpret the structured "## Research Requirements"
            # block as a meta-description and respond with a generic "I'm ready
            # to help" introduction (observed Apr 2026 with sonnet-4.6 + 24 tools).
            prompt = f"""# Symbol Research: {symbol}

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

LANGUAGE REQUIREMENT:
Respond in Simplified Chinese (简体中文).
Technical terms can include English in parentheses for clarity.
"""

            # Apply context window management (sliding window + summary)
            conversation_history = []
            if historical_messages:
                total_tokens = self.context_manager.calculate_context_tokens(
                    historical_messages
                )
                model = getattr(self.settings, "dashscope_model", "qwen-plus")

                if self.context_manager.should_compact(total_tokens, model=model):
                    logger.info(
                        "Context compaction triggered",
                        symbol=symbol,
                        total_tokens=total_tokens,
                        message_count=len(historical_messages),
                    )

                    head, body, tail = self.context_manager.extract_context_structure(
                        historical_messages
                    )
                    summary_text = await self.context_manager.summarize_history(
                        body_messages=body,
                        symbol=symbol,
                        llm_service=self.react_agent,
                    )
                    compacted_messages = self.context_manager.reconstruct_context(
                        head=head,
                        summary_text=summary_text,
                        tail=tail,
                    )

                    for msg in compacted_messages:
                        conversation_history.append(
                            {"role": msg.role, "content": msg.content}
                        )

                    logger.info(
                        "Context compacted successfully",
                        symbol=symbol,
                        original_tokens=total_tokens,
                        compacted_count=len(compacted_messages),
                    )
                else:
                    # Use full history (under threshold)
                    for msg in historical_messages:
                        conversation_history.append(
                            {"role": msg.role, "content": msg.content}
                        )

            # NOTE: Do NOT add prompt to conversation_history here!
            # ainvoke() will add it with language instruction - adding here causes duplicate

            # Invoke ReAct agent for research (tools enabled)
            logger.info(
                "Invoking agent for symbol research",
                symbol=symbol,
                conversation_history_length=len(conversation_history),
            )
            response = await self.react_agent.ainvoke(
                prompt, conversation_history=conversation_history
            )

            # Parse response
            if isinstance(response, dict) and "final_answer" in response:
                response_text = response["final_answer"]
            else:
                response_text = str(response)

            # Extract token usage
            input_tokens = 0
            output_tokens = 0
            if isinstance(response, dict):
                usage = response.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)

            # Create analysis message (pure research, no decision)
            # Note: analysis_type param is source ("holding"/"watchlist"), but we store
            # "individual" for filtering purposes (vs "portfolio" for Phase 2 decisions)
            source_emoji_map = {"holding": "💼", "watchlist": "👀"}
            source_emoji = source_emoji_map.get(analysis_type, "📊")

            message_content = f"## {source_emoji} Symbol Research - {symbol}\n\n"
            message_content += (
                f"**Source:** {analysis_type.replace('_', ' ').title()}\n"
            )
            message_content += f"**Analysis ID:** {analysis_id}\n\n"
            message_content += f"{response_text}\n"

            metadata = MessageMetadata(
                symbol=symbol,
                interval="1d",
                analysis_id=analysis_id,
                analysis_type="individual",  # Phase 1 = individual symbol research
            )

            message_create = MessageCreate(
                chat_id=chat_id,
                role="assistant",
                content=message_content,
                source="llm",
                metadata=metadata,
            )
            message = (
                None
                if suppress_chat
                else await self.message_repo.create(message_create)
            )

            logger.info(
                "Phase 1: Symbol research completed",
                symbol=symbol,
                analysis_type=analysis_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            # Return research result (no decision - that comes in Phase 2)
            return SymbolAnalysisResult(
                symbol=symbol,
                analysis_type=analysis_type,
                analysis_text=response_text,
                analysis_id=analysis_id,
                chat_id=chat_id,
                message_id=message.message_id if message else None,
            )

        except Exception as e:
            logger.error(
                "Symbol research failed",
                symbol=symbol,
                analysis_type=analysis_type,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return None

    async def _get_symbol_chat_id(
        self, symbol: str, user_id: str = "portfolio_agent"
    ) -> str:
        """
        Get or create a dedicated chat for this symbol.

        CRITICAL: Portfolio agent chats MUST be owned by "portfolio_agent" user, NOT individual users.

        This ensures:
        1. Chats appear in Portfolio Dashboard only (not personal chat)
        2. All users see the same portfolio analysis history
        3. No chat duplication across users
        4. Proper auth isolation between personal and portfolio chats

        Args:
            symbol: Stock symbol
            user_id: MUST be "portfolio_agent" (system user) - defaults to "portfolio_agent"

        Returns:
            Chat ID for this symbol
        """
        # Force portfolio_agent as owner (ignore passed user_id for safety)
        owner_id = "portfolio_agent"

        # Try to find existing chat for this symbol
        chats = await self.chat_repo.list_by_user(owner_id)
        for chat in chats:
            if chat.title and chat.title.startswith(f"{symbol} "):
                logger.info(
                    "Found existing chat for symbol",
                    symbol=symbol,
                    owner=owner_id,
                    chat_id=chat.chat_id,
                )
                return chat.chat_id

        # Create new chat for this symbol
        chat_create = ChatCreate(
            title=f"{symbol} Analysis",
            user_id=owner_id,
        )
        chat = await self.chat_repo.create(chat_create)
        logger.info(
            "Created new chat for symbol",
            symbol=symbol,
            owner=owner_id,
            chat_id=chat.chat_id,
        )
        return chat.chat_id

    async def _run_phase1_research(
        self,
        positions: list[Any],
        watchlist_items: list[Any],
        user_id: str,
        dry_run: bool,
        result_summary: dict[str, Any],
        suppress_chat: bool = False,
    ) -> list[SymbolAnalysisResult]:
        """
        Run Phase 1: Independent symbol research (concurrent, pure analysis).

        Args:
            positions: List of position-like objects (must have .symbol)
            watchlist_items: List of watchlist-like objects (must have .symbol)
            user_id: User ID for tracking
            dry_run: If True, skip actual analysis
            result_summary: Result summary dict to update
            suppress_chat: When True, per-symbol chat/message rows are NOT
                written; SymbolAnalysisResult.analysis_text still carries
                the full research. Used by dashboard two-button flows.

        Returns:
            List of SymbolAnalysisResult from all analyses
        """
        all_analysis_results: list[SymbolAnalysisResult] = []
        analyzed_symbols: set[str] = set()

        # Analyze holdings - BATCH PROCESSING
        if positions:
            if dry_run:
                for position in positions:
                    logger.info(
                        "Dry run - would research holding",
                        symbol=position.symbol,
                    )
                    result_summary["holdings_analyzed"] += 1
                    analyzed_symbols.add(position.symbol)
            else:
                holdings_tasks = [
                    self._analyze_symbol(
                        symbol=position.symbol,
                        user_id=user_id,
                        analysis_type="holding",
                        suppress_chat=suppress_chat,
                    )
                    for position in positions
                ]

                batch_size = self.settings.portfolio_analysis_batch_size
                for i in range(0, len(holdings_tasks), batch_size):
                    batch = holdings_tasks[i : i + batch_size]
                    results = await asyncio.gather(*batch, return_exceptions=True)

                    for idx, result in enumerate(results):
                        symbol = positions[i + idx].symbol
                        if isinstance(result, Exception):
                            logger.error(
                                "Failed to research holding",
                                symbol=symbol,
                                error=str(result),
                            )
                            result_summary["errors"].append(
                                {"type": "holding", "symbol": symbol}
                            )
                        elif result is not None:
                            all_analysis_results.append(result)
                            result_summary["holdings_analyzed"] += 1
                            analyzed_symbols.add(symbol)
                        else:
                            result_summary["errors"].append(
                                {"type": "holding", "symbol": symbol}
                            )

        # Analyze watchlist - BATCH PROCESSING (with deduplication)
        if watchlist_items:
            unique_watchlist_items = [
                item for item in watchlist_items if item.symbol not in analyzed_symbols
            ]

            if len(unique_watchlist_items) < len(watchlist_items):
                skipped_count = len(watchlist_items) - len(unique_watchlist_items)
                logger.info(
                    "Skipping watchlist items already analyzed as holdings",
                    skipped_count=skipped_count,
                )

            if dry_run:
                for watchlist_item in unique_watchlist_items:
                    logger.info(
                        "Dry run - would research watchlist item",
                        symbol=watchlist_item.symbol,
                    )
                    result_summary["watchlist_analyzed"] += 1
                    analyzed_symbols.add(watchlist_item.symbol)
            else:
                watchlist_tasks = [
                    self._analyze_symbol(
                        symbol=watchlist_item.symbol,
                        user_id=user_id,
                        analysis_type="watchlist",
                        suppress_chat=suppress_chat,
                    )
                    for watchlist_item in unique_watchlist_items
                ]

                batch_size = self.settings.portfolio_analysis_batch_size
                for i in range(0, len(watchlist_tasks), batch_size):
                    batch = watchlist_tasks[i : i + batch_size]
                    results = await asyncio.gather(*batch, return_exceptions=True)

                    for idx, result in enumerate(results):
                        watchlist_item = unique_watchlist_items[i + idx]
                        if isinstance(result, Exception):
                            logger.error(
                                "Failed to research watchlist item",
                                symbol=watchlist_item.symbol,
                                error=str(result),
                            )
                            result_summary["errors"].append(
                                {
                                    "type": "watchlist",
                                    "symbol": watchlist_item.symbol,
                                }
                            )
                        elif result is not None:
                            all_analysis_results.append(result)
                            result_summary["watchlist_analyzed"] += 1
                            analyzed_symbols.add(watchlist_item.symbol)
                            # Picks flow passes _SymbolStub objects (no
                            # watchlist_id) for sector-filtered candidates
                            # that aren't actually in the user's watchlist —
                            # nothing to update there. Only stamp last-analyzed
                            # on real WatchlistItem objects.
                            wl_id = getattr(watchlist_item, "watchlist_id", None)
                            if wl_id is not None:
                                await self.watchlist_repo.update_last_analyzed(
                                    wl_id,
                                    user_id,
                                    utcnow(),
                                )
                        else:
                            result_summary["errors"].append(
                                {
                                    "type": "watchlist",
                                    "symbol": watchlist_item.symbol,
                                }
                            )

        # Calculate total
        result_summary["total_symbols_analyzed"] = (
            result_summary["holdings_analyzed"] + result_summary["watchlist_analyzed"]
        )

        logger.info(
            "Phase 1 complete: Symbol research finished",
            user_id=user_id,
            total_analyzed=result_summary["total_symbols_analyzed"],
            holdings=result_summary["holdings_analyzed"],
            watchlist=result_summary["watchlist_analyzed"],
            analysis_results_count=len(all_analysis_results),
        )

        return all_analysis_results
