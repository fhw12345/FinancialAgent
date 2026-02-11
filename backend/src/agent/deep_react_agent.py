"""
Deep ReAct Agent with Hierarchical Sub-Agent Delegation.

Orchestrates specialist sub-agents (Technical, News, Financial)
with optional adversarial debate loop. Supports structured event
emission via on_event callback for real-time SSE streaming.

Flow: User → [Sub-Agents] → [Debate ↔ Rebuttal] → Verdict
"""

import operator
import time
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

import structlog
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from ..api.schemas.deep_agent_events import (
    DeepEventEmitter,
    extract_risk_level,
)
from ..core.utils.token_utils import extract_token_usage_from_messages
from .context import AgentContext
from .subagent_invoker import invoke_subagent
from .subagents.debater import TERMINATION_SIGNAL, create_debater_subagent
from .subagents.financial import create_financial_subagent
from .subagents.news import create_news_subagent
from .subagents.technical import create_technical_subagent
from .tools.categorization import get_all_tools_dict

logger = structlog.get_logger()

DEFAULT_MAX_DEBATE_ROUNDS = 2


class AnalysisState(TypedDict, total=False):
    """
    Typed state for the analysis workflow.

    Using TypedDict instead of dataclass for better LangGraph compatibility.
    State flows between nodes; runtime config (dates, user_id) flows via RunnableConfig.
    """

    # Message history (accumulates via operator.add)
    messages: Annotated[list[BaseMessage], operator.add]
    # Target symbol for analysis
    symbol: str
    # Current debate round
    round_count: int
    # Research report from synthesis
    research_report: str
    # Whether debate loop is active
    debate_active: bool


class DeepReActAgent:
    """
    Hierarchical agent with sub-agent delegation and optional debate loop.

    This agent orchestrates specialist sub-agents, each of which uses
    the Skills pattern for strategic tool usage.
    """

    def __init__(
        self,
        settings: Any,
        tools: list[Any],
        enable_debate: bool = True,
        max_debate_rounds: int = DEFAULT_MAX_DEBATE_ROUNDS,
    ):
        """
        Initialize the Deep ReAct Agent.

        Args:
            settings: Application settings with API keys
            tools: List of all available tools
            enable_debate: Whether to enable the adversarial debate loop
            max_debate_rounds: Maximum number of debate iterations
        """
        self.settings = settings
        self.enable_debate = enable_debate
        self.max_debate_rounds = max_debate_rounds

        # Convert tools to dict for skill creation
        self.tools_dict = get_all_tools_dict(tools)

        # Initialize LLM
        self.llm = ChatTongyi(
            model_name=settings.default_llm_model,
            dashscope_api_key=settings.dashscope_api_key,
            temperature=settings.default_llm_temperature,
            model_kwargs={"result_format": "message"},
            request_timeout=30,
        )

        logger.info(
            "DeepReActAgent initialized",
            enable_debate=enable_debate,
            max_debate_rounds=max_debate_rounds,
            total_tools=len(tools),
        )

    def _create_subagents(self, context: AgentContext) -> dict[str, Any]:
        """Create all sub-agents with context.

        Each sub-agent is a DeepSubAgent wrapping a deepagents compiled graph
        with domain-specific tools and SKILL.md files.
        """
        return {
            "technical": create_technical_subagent(self.tools_dict, self.llm, context),
            "news": create_news_subagent(self.tools_dict, self.llm, context),
            "financial": create_financial_subagent(self.tools_dict, self.llm, context),
            "debater": create_debater_subagent(self.tools_dict, self.llm, context),
        }

    def _build_workflow(
        self,
        context: AgentContext,
        emitter: DeepEventEmitter | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> StateGraph:
        """Build the LangGraph workflow.

        Args:
            context: Agent context with session parameters
            emitter: Event emitter for sequenced event creation
            on_event: Callback to emit events to the streaming layer
        """
        subagents = self._create_subagents(context)

        def _emit(event: dict[str, Any]) -> None:
            """Safely emit an event via callback."""
            if on_event is not None:
                try:
                    on_event(event)
                except Exception:
                    logger.warning("Failed to emit event", event_type=event.get("type"))

        # Node functions - receive config via LangGraph's automatic config passing
        async def research_node(state: dict, config: RunnableConfig) -> dict:
            """Run parallel research with specialist sub-agents."""
            symbol = state.get("symbol", context.symbol)
            configurable = config.get("configurable", {})

            logger.info(
                "Starting research phase",
                symbol=symbol,
                session_id=configurable.get("session_id"),
                current_date=configurable.get("current_date"),
            )

            # Sub-agent invocation sequence with event emission
            research_tasks = [
                (
                    "technical",
                    f"Analyze the technical setup for {symbol}. "
                    f"Focus on trend, Fibonacci levels, and momentum.",
                ),
                (
                    "news",
                    f"Analyze recent news and sentiment for {symbol}. "
                    f"Include catalyst assessment and market mood.",
                ),
                (
                    "financial",
                    f"Analyze the fundamentals of {symbol}. "
                    f"Focus on valuation, cash flow health, and earnings quality.",
                ),
            ]

            reports: dict[str, str] = {}
            for subagent_key, prompt in research_tasks:
                report, _ = await self._invoke_with_events(
                    subagents[subagent_key],
                    prompt,
                    config=config,
                    emitter=emitter,
                    on_event=on_event,
                    emit_fn=_emit,
                )
                reports[subagent_key] = report

            # Emit synthesis start (signals sub-agents done, moving to debate)
            if emitter:
                _emit(emitter.synthesis_start())

            # Pass sub-agent reports through directly — the verdict node
            # handles final synthesis + judgment as the orchestrator's concluding step.
            report = f"""## Technical Analysis
{reports.get("technical", "N/A")}

## News & Sentiment Analysis
{reports.get("news", "N/A")}

## Fundamental Analysis
{reports.get("financial", "N/A")}"""

            logger.info(
                "Research phase complete",
                symbol=symbol,
                report_length=len(report),
            )

            return {
                "messages": [AIMessage(content=report, name="Researcher")],
                "research_report": report,
                "round_count": state.get("round_count", 0) + 1,
            }

        async def debate_node(state: dict, config: RunnableConfig) -> dict:
            """Run adversarial analysis with debater sub-agent."""
            report = state.get("research_report", "")
            round_count = state.get("round_count", 1)
            configurable = config.get("configurable", {})

            logger.info(
                "Starting debate phase",
                round=round_count,
                session_id=configurable.get("session_id"),
            )

            # Emit debate start event
            if emitter:
                _emit(emitter.debate_start(round_count, self.max_debate_rounds))

            critique_prompt = f"""Review the following investment thesis and challenge it:

{report[:3000]}

Your job is to:
1. Use your fact-checking skills to verify key claims
2. Search for counter-evidence and contradicting data
3. Identify overlooked risks and stress-test assumptions

Be aggressive but fair. Use real evidence, not speculation.

If after thorough review you genuinely have no concerns, respond with:
"{TERMINATION_SIGNAL}"
"""

            critique, _tool_count = await self._invoke_with_events(
                subagents["debater"],
                critique_prompt,
                config=config,
                emitter=emitter,
                on_event=on_event,
                emit_fn=_emit,
            )

            has_concerns = TERMINATION_SIGNAL not in critique
            logger.info(
                "Debate round complete",
                round=round_count,
                has_concerns=has_concerns,
            )

            # Emit debate round result
            if emitter:
                _emit(emitter.debate_round(round_count, has_concerns, critique))

            return {
                "messages": [AIMessage(content=critique, name="Debater")],
                "round_count": round_count,  # Explicitly preserve to prevent state loss
                "research_report": report,  # Prevent LangGraph state loss
            }

        async def rebuttal_node(state: dict, config: RunnableConfig) -> dict:
            """Defend the thesis against debater concerns with evidence.

            Uses a subset of sub-agents (technical + financial) to gather
            targeted evidence addressing each specific concern raised.
            """
            messages = state.get("messages", [])
            report = state.get("research_report", "")
            round_count = state.get("round_count", 1)

            # Extract debater's critique from last message
            critique = ""
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, "content"):
                    critique = last_msg.content

            logger.info(
                "Starting rebuttal phase",
                round=round_count,
                critique_length=len(critique),
            )

            if emitter:
                _emit(emitter.rebuttal_start(round_count))

            rebuttal_start = time.perf_counter()

            # Build focused rebuttal prompt targeting each concern
            rebuttal_prompt = f"""The debater raised the following concerns about the investment thesis for {state.get("symbol", "")}:

--- DEBATER CRITIQUE ---
{critique[:2000]}
--- END CRITIQUE ---

Your job is to DEFEND the thesis by addressing each concern with evidence:
1. For each concern, use tools to gather SPECIFIC data that confirms or refutes it
2. If the concern is valid, acknowledge it and explain why the thesis still holds
3. If the concern is wrong, provide evidence that disproves it
4. Be concise — focus on DATA, not rhetoric

Respond with a structured defense addressing each concern point-by-point."""

            # Use financial sub-agent for evidence gathering (most fact-checking tools)
            defense_parts: list[str] = []
            total_tool_count = 0

            for subagent_key in ("financial",):
                defense, actual_tool_count = await self._invoke_with_events(
                    subagents[subagent_key],
                    rebuttal_prompt,
                    config=config,
                    emitter=emitter,
                    on_event=on_event,
                    emit_fn=_emit,
                    raise_on_error=False,
                )
                if defense:
                    defense_parts.append(defense)
                    total_tool_count += actual_tool_count
                else:
                    logger.warning(
                        "Rebuttal sub-agent failed, continuing with partial defense",
                        subagent=subagent_key,
                    )

            combined_defense = "\n\n".join(defense_parts)
            rebuttal_duration = int((time.perf_counter() - rebuttal_start) * 1000)

            if emitter:
                _emit(
                    emitter.rebuttal_result(
                        current_round=round_count,
                        defense_summary=combined_defense,
                        tool_count=total_tool_count,
                        duration_ms=rebuttal_duration,
                    )
                )

            # Update research report with defense incorporated
            updated_report = f"""{report}

## Defense (Round {round_count})
{combined_defense}"""

            logger.info(
                "Rebuttal phase complete",
                round=round_count,
                tool_count=total_tool_count,
                duration_ms=rebuttal_duration,
            )

            return {
                "messages": [AIMessage(content=combined_defense, name="Defender")],
                "research_report": updated_report,
                "round_count": round_count + 1,
            }

        def should_continue(state: dict) -> str:
            """Determine if debate should continue."""
            messages = state.get("messages", [])
            round_count = state.get("round_count", 1)

            # Check max rounds
            if round_count >= self.max_debate_rounds:
                logger.info("Max debate rounds reached", rounds=round_count)
                return "end"

            # Check for termination signal in last debater message
            if messages:
                last_message = messages[-1]
                if hasattr(last_message, "content"):
                    if TERMINATION_SIGNAL in last_message.content:
                        logger.info("Debater satisfied, ending debate")
                        return "end"

            logger.info("Continuing debate", round=round_count + 1)
            return "continue"

        async def verdict_node(state: dict, config: RunnableConfig) -> dict:
            """Synthesize debate into a final actionable verdict.

            Single LLM call (no tools) that categorizes each debater concern
            and produces a Buy/Hold/Sell recommendation with conviction level.
            """
            report = state.get("research_report", "")
            messages = state.get("messages", [])
            round_count = state.get("round_count", 1)

            # Collect debate exchanges (Debater + Defender messages)
            debate_exchanges: list[str] = []
            for msg in messages:
                name = getattr(msg, "name", "")
                if name in ("Debater", "Defender") and hasattr(msg, "content"):
                    debate_exchanges.append(f"**{name}**:\n{msg.content}")

            debate_text = "\n\n---\n\n".join(debate_exchanges) if debate_exchanges else "No debate occurred."

            logger.info(
                "Starting verdict phase",
                round_count=round_count,
                debate_exchange_count=len(debate_exchanges),
            )

            if emitter:
                _emit(emitter.synthesis_start())

            # Extract original research (before defense appendages) to avoid
            # double-vision where defense content appears in both report and debate_text
            parts = report.split("\n\n## Defense (Round")
            original_research = parts[0].strip()

            verdict_prompt = f"""You are a Senior Investment Committee Judge delivering a final verdict.

You have reviewed:
1. A comprehensive research report
2. {len(debate_exchanges)} debate exchanges between a Debater and Defender

## Research Report
{original_research[:6000]}

## Debate Exchanges
{debate_text[:4000]}

## Your Task

For EACH concern raised by the Debater, categorize it:
- ✅ **VERIFIED**: [concern] — [1-sentence reasoning citing specific data]
- ⚠️ **NEEDS MORE EVIDENCE**: [concern] — [what data is missing]
- ❌ **CONTRADICTED**: [concern] — [evidence that disproves it]

Then provide your final verdict:

### Final Verdict
- **Action**: Buy / Hold / Sell
- **Conviction**: High / Medium / Low
- **Risk Level**: HIGH / MODERATE / LOW
- **Key Insight**: 1-2 sentences on the most important takeaway

Be decisive. Use the evidence from both sides. Do not hedge excessively."""

            verdict_response = await self.llm.ainvoke(
                [HumanMessage(content=verdict_prompt)],
                config=config,
            )

            verdict_text = verdict_response.content
            logger.info(
                "Verdict phase complete",
                verdict_length=len(verdict_text),
            )

            return {
                "messages": [AIMessage(content=verdict_text, name="Judge")],
                "research_report": verdict_text,  # Becomes final_answer via adapter
                "round_count": round_count,
            }

        # Build graph
        builder = StateGraph(dict)

        builder.add_node("research", research_node)
        builder.add_edge(START, "research")

        if self.enable_debate:
            builder.add_node("debate", debate_node)
            builder.add_node("rebuttal", rebuttal_node)
            builder.add_node("verdict", verdict_node)
            builder.add_edge("research", "debate")
            builder.add_edge("rebuttal", "debate")
            builder.add_conditional_edges(
                "debate",
                should_continue,
                {
                    "continue": "rebuttal",  # Defense with evidence
                    "end": "verdict",  # Final synthesis with concern categorization
                },
            )
            builder.add_edge("verdict", END)
        else:
            builder.add_edge("research", END)

        return builder.compile()

    async def _invoke_subagent(
        self,
        subagent: Any,
        prompt: str,
        config: RunnableConfig | None = None,
        emitter: DeepEventEmitter | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, int]:
        """Invoke a deep sub-agent with retry logic.

        The sub-agent's deepagents graph already includes the LLM model,
        built-in tools, custom tools, and skills middleware.

        Returns:
            Tuple of (response_content, tool_count).
        """
        return await invoke_subagent(
            subagent=subagent,
            prompt=prompt,
            config=config,
            emitter=emitter,
            on_event=on_event,
        )

    async def _invoke_with_events(
        self,
        subagent: Any,
        prompt: str,
        *,
        config: RunnableConfig | None = None,
        emitter: DeepEventEmitter | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        emit_fn: Callable[[dict[str, Any]], None] | None = None,
        raise_on_error: bool = True,
    ) -> tuple[str, int]:
        """Invoke a sub-agent with lifecycle event emission and timing.

        Wraps _invoke_subagent with the common pattern of:
        subagent_start → invoke → subagent_result (success/error).

        Args:
            subagent: The DeepSubAgent to invoke
            prompt: Task prompt for the sub-agent
            config: LangGraph RunnableConfig for tracing
            emitter: Event factory for creating sequenced events
            on_event: Raw callback for streaming events to SSE
            emit_fn: Safe emit wrapper (captures on_event closure)
            raise_on_error: If True, re-raise exceptions after emitting error event

        Returns:
            Tuple of (response_content, tool_count).
        """
        subagent_name = subagent.config.name

        if emitter and emit_fn:
            emit_fn(emitter.subagent_start(subagent_name, subagent.get_tool_names()))

        sa_start = time.perf_counter()
        try:
            result, tool_count = await self._invoke_subagent(
                subagent, prompt, config=config, emitter=emitter, on_event=on_event,
            )
            sa_duration = int((time.perf_counter() - sa_start) * 1000)

            if emitter and emit_fn:
                emit_fn(emitter.subagent_result(
                    subagent_name=subagent_name,
                    status="success",
                    duration_ms=sa_duration,
                    result_summary=result,
                    tool_count=tool_count,
                ))
            return result, tool_count

        except Exception as e:
            sa_duration = int((time.perf_counter() - sa_start) * 1000)
            if emitter and emit_fn:
                emit_fn(emitter.subagent_result(
                    subagent_name=subagent_name,
                    status="error",
                    duration_ms=sa_duration,
                    result_summary=str(e),
                ))
            if raise_on_error:
                raise
            return "", 0

    async def analyze(
        self,
        symbol: str,
        user_id: str = "anonymous",
        enable_debate: bool | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        user_message: str | None = None,
    ) -> dict[str, Any]:
        """Run a full analysis for a symbol with optional event streaming.

        Args:
            symbol: Target ticker symbol
            user_id: Authenticated user ID
            enable_debate: Override debate setting (None = use default)
            on_event: Callback for streaming lifecycle events
            user_message: The user's actual question (used as initial state message)
        """
        context = AgentContext(
            symbol=symbol,
            user_id=user_id,
            enable_debate=(
                enable_debate if enable_debate is not None else self.enable_debate
            ),
        )

        emitter = DeepEventEmitter() if on_event else None
        workflow = self._build_workflow(context, emitter=emitter, on_event=on_event)

        config = RunnableConfig(
            configurable=context.to_dict(),
            tags=[f"symbol:{symbol}", f"user:{user_id}"],
            metadata={
                "agent_type": "DeepReActAgent",
                "analysis_type": context.analysis_type,
            },
        )

        # Use the real user message; fall back to a generic prompt for API-only usage
        initial_content = user_message or f"Analyze {symbol} comprehensively."

        initial_state: AnalysisState = {
            "messages": [HumanMessage(content=initial_content)],
            "symbol": symbol,
            "round_count": 0,
            "research_report": "",
            "debate_active": context.enable_debate,
        }

        def _safe_emit(event: dict[str, Any]) -> None:
            """Safely emit an event via callback (outside workflow nodes).

            Same logic as _emit() inside _build_workflow — both are closures
            over on_event but in different scopes (analyze vs workflow nodes).
            """
            if on_event is not None:
                try:
                    on_event(event)
                except Exception:
                    logger.warning("Failed to emit event", event_type=event.get("type"))

        if emitter and on_event:
            subagent_names = ["technical_analyst", "news_analyst", "financial_analyst"]
            _safe_emit(emitter.deep_start(symbol, subagent_names, context.enable_debate))

        start_time = time.perf_counter()
        logger.info(
            "Starting analysis",
            symbol=symbol,
            session_id=context.session_id,
            current_date=context.current_date,
            enable_debate=context.enable_debate,
        )

        try:
            final_state = await workflow.ainvoke(initial_state, config=config)
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "Analysis failed",
                symbol=symbol,
                session_id=context.session_id,
                error=str(e),
                duration_ms=duration_ms,
            )
            raise

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        all_messages = final_state.get("messages", [])
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            all_messages
        )

        logger.info(
            "Analysis complete",
            symbol=symbol,
            session_id=context.session_id,
            total_rounds=final_state.get("round_count", 0),
            message_count=len(all_messages),
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

        final_state["input_tokens"] = input_tokens
        final_state["output_tokens"] = output_tokens
        final_state["total_tokens"] = total_tokens
        final_state["agent_duration_ms"] = duration_ms

        if emitter and on_event:
            report = final_state.get("research_report", "")
            risk_level = extract_risk_level(report)
            tool_count = sum(
                1 for m in all_messages if m.__class__.__name__ == "ToolMessage"
            )
            _safe_emit(
                emitter.verdict(
                    verdict_text=report,
                    risk_level=risk_level,
                    tool_count=tool_count,
                    total_duration_ms=duration_ms,
                )
            )

        return final_state
