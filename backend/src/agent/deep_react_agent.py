"""
Deep ReAct Agent with Hierarchical Sub-Agent Delegation.

Orchestrates specialist sub-agents (Technical, News, Financial)
with optional adversarial debate loop. Supports structured event
emission via on_event callback for real-time SSE streaming.

Flow: User → [Main Agent] → [Debate ↔ Rebuttal] → Verdict
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
from .debate_types import (
    Concern,
    Rebuttal,
    merge_facts,
    parse_debater_output,
    parse_rebuttal_output,
    render_verified_facts_reminder,
)
from .subagent_invoker import invoke_subagent
from .subagents.debater import TERMINATION_SIGNAL, create_debater_subagent
from .subagents.financial import create_financial_subagent
from .subagents.news import create_news_subagent
from .subagents.technical import create_technical_subagent
from .tools.analysis_cache import AnalysisToolCache
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
    # Structured debate exchange (auto-accumulated via operator.add reducer)
    all_concerns: Annotated[list, operator.add]  # Concern dicts from debater
    all_rebuttals: Annotated[list, operator.add]  # Rebuttal dicts from defender


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

        # Exa API key for debater's independent web search
        self.exa_api_key: str = getattr(settings, "exa_api_key", "")

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

    def _create_subagents(
        self,
        context: AgentContext,
        cache: AnalysisToolCache | None = None,
    ) -> dict[str, Any]:
        """Create all sub-agents with context and optional tool cache."""
        return {
            "technical": create_technical_subagent(
                self.tools_dict, self.llm, context, cache=cache
            ),
            "news": create_news_subagent(
                self.tools_dict, self.llm, context, cache=cache
            ),
            "financial": create_financial_subagent(
                self.tools_dict, self.llm, context, cache=cache
            ),
            "debater": create_debater_subagent(
                model=self.llm, context=context, exa_api_key=self.exa_api_key
            ),
        }

    def _build_workflow(
        self,
        context: AgentContext,
        cache: AnalysisToolCache,
        emitter: DeepEventEmitter | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> StateGraph:
        """Build the LangGraph workflow with symmetric debate topology.

        Graph topology (debate enabled):
            START → main_agent → debate → should_continue
                                   ↑            |
                                   |    continue → main_agent (rebuttal)
                                   |    end → verdict → END

        Round semantics:
        - round_count starts at 0
        - main_agent_node does NOT increment (research or rebuttal)
        - debate_node increments after challenging
        - should_continue checks after debater

        Args:
            context: Agent context with session parameters
            cache: Per-analysis tool result cache (created in analyze())
            emitter: Event emitter for sequenced event creation
            on_event: Callback to emit events to the streaming layer
        """
        subagents = self._create_subagents(context, cache=cache)

        def _emit(event: dict[str, Any]) -> None:
            """Safely emit an event via callback."""
            if on_event is not None:
                try:
                    on_event(event)
                except Exception:
                    logger.warning("Failed to emit event", event_type=event.get("type"))

        # ── main_agent_node ──────────────────────────────────────────────
        async def main_agent_node(state: dict, config: RunnableConfig) -> dict:
            """Run research (round 0) or rebuttal (round > 0).

            First invocation: Sequential research across tech, news, financial.
            Subsequent invocations: Targeted rebuttal addressing debater concerns.
            """
            symbol = state.get("symbol", context.symbol)
            round_count = state.get("round_count", 0)
            configurable = config.get("configurable", {})

            if round_count == 0:
                # ── RESEARCH PHASE ──
                logger.info(
                    "Starting research phase",
                    symbol=symbol,
                    session_id=configurable.get("session_id"),
                    current_date=configurable.get("current_date"),
                )

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

                # Only emit synthesis_start when debate is disabled (straight to END).
                # When debate IS enabled, verdict_node emits synthesis_start instead.
                if emitter and not self.enable_debate:
                    _emit(emitter.synthesis_start())

                combined_report = f"""## Technical Analysis
{reports.get("technical", "N/A")}

## News & Sentiment Analysis
{reports.get("news", "N/A")}

## Fundamental Analysis
{reports.get("financial", "N/A")}"""

                logger.info(
                    "Research phase complete",
                    symbol=symbol,
                    report_length=len(combined_report),
                )

                return {
                    "messages": [AIMessage(content=combined_report, name="Researcher")],
                    "research_report": combined_report,
                    "round_count": round_count,
                    # Empty lists — operator.add reducer accumulates automatically
                    "all_concerns": [],
                    "all_rebuttals": [],
                }

            # ── REBUTTAL PHASE ──
            # Read accumulated concerns from state (populated by operator.add reducer)
            all_concerns = state.get("all_concerns", [])

            logger.info(
                "Starting rebuttal phase",
                round=round_count,
                concern_count=len(all_concerns),
            )

            if emitter:
                _emit(emitter.rebuttal_start(round_count))

            rebuttal_start_time = time.perf_counter()

            # Build targeted rebuttal from structured concerns
            concern_lines = "\n".join(
                f"- [{c.get('severity', 'MAJOR')}] {c.get('id', '?')}: "
                f"{c.get('claim', '')} — {c.get('challenge', '')}"
                for c in all_concerns
            )

            rebuttal_prompt = f"""The debater raised concerns about {symbol}:

{concern_lines}

Your job is to DEFEND the thesis by addressing each concern with evidence:
1. For each concern, use tools to gather SPECIFIC data that confirms or refutes it
2. If the concern is valid, acknowledge it and explain why the thesis still holds
3. If the concern is wrong, provide evidence that disproves it

RESPONSE FORMAT: Include a JSON block in your response:
```json
{{
  "rebuttals": [
    {{
      "concern_id": "C1",
      "status": "REFUTED|PARTIALLY_VALID|CONCEDED",
      "defense": "Your defense with specific data",
      "evidence": "Source of your evidence"
    }}
  ]
}}
```

Be concise — focus on DATA, not rhetoric."""

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
                        "Rebuttal sub-agent failed",
                        subagent=subagent_key,
                    )

            combined_defense = "\n\n".join(defense_parts)
            rebuttal_duration = int((time.perf_counter() - rebuttal_start_time) * 1000)

            # Parse structured rebuttal output
            rebuttal_output = parse_rebuttal_output(combined_defense)
            new_rebuttals = [
                {
                    "concern_id": r.concern_id,
                    "status": r.status,
                    "defense": r.defense,
                    "evidence": r.evidence,
                }
                for r in rebuttal_output.rebuttals
            ]

            if emitter:
                _emit(
                    emitter.rebuttal_result(
                        current_round=round_count,
                        defense_summary=combined_defense,
                        tool_count=total_tool_count,
                        duration_ms=rebuttal_duration,
                        rebuttals=new_rebuttals,
                    )
                )

            updated_report = (
                f"{state.get('research_report', '')}"
                f"\n\n## Defense (Round {round_count})\n{combined_defense}"
            )

            logger.info(
                "Rebuttal phase complete",
                round=round_count,
                tool_count=total_tool_count,
                parsed_rebuttals=len(new_rebuttals),
                duration_ms=rebuttal_duration,
            )

            return {
                "messages": [AIMessage(content=combined_defense, name="Defender")],
                "research_report": updated_report,
                "round_count": round_count,
                # Only return NEW items — operator.add reducer handles accumulation
                "all_concerns": [],
                "all_rebuttals": new_rebuttals,
            }

        # ── debate_node ──────────────────────────────────────────────────
        async def debate_node(state: dict, config: RunnableConfig) -> dict:
            """Run adversarial analysis with structured concern parsing.

            Invokes the debater sub-agent (with independent yfinance + Exa tools)
            and parses its structured JSON output into programmatic concerns.
            """
            report = state.get("research_report", "")
            round_count = state.get("round_count", 0)
            configurable = config.get("configurable", {})

            logger.info(
                "Starting debate phase",
                round=round_count + 1,
                session_id=configurable.get("session_id"),
            )

            if emitter:
                _emit(emitter.debate_start(round_count + 1, self.max_debate_rounds))

            # Truncate at sentence boundary to avoid cutting mid-word/mid-JSON
            max_len = 3000
            truncated_report = report[:max_len]
            if len(report) > max_len:
                last_period = truncated_report.rfind(".")
                if last_period > max_len // 2:
                    truncated_report = truncated_report[: last_period + 1]

            critique_prompt = f"""Review the following investment thesis and challenge it:

{truncated_report}

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

            # Parse structured debater output
            debater_output = parse_debater_output(critique)
            new_concerns = [
                {
                    "id": c.id,
                    "claim": c.claim,
                    "category": c.category,
                    "challenge": c.challenge,
                    "severity": c.severity,
                    "evidence": c.evidence,
                }
                for c in debater_output.concerns
            ]

            has_concerns = not debater_output.terminated and len(new_concerns) > 0
            new_round = round_count + 1

            logger.info(
                "Debate round complete",
                round=new_round,
                has_concerns=has_concerns,
                parsed_concerns=len(new_concerns),
                terminated=debater_output.terminated,
            )

            if emitter:
                _emit(
                    emitter.debate_round(
                        new_round, has_concerns, critique, concerns=new_concerns
                    )
                )

            return {
                "messages": [AIMessage(content=critique, name="Debater")],
                "round_count": new_round,
                "research_report": report,
                # Only return NEW concerns — operator.add reducer handles accumulation
                "all_concerns": new_concerns,
                "all_rebuttals": [],
                "debate_active": not debater_output.terminated,
            }

        # ── should_continue ──────────────────────────────────────────────
        def should_continue(state: dict) -> str:
            """Determine if debate should continue based on debater output.

            Returns "continue" for normal rounds, "final_rebuttal" when max
            rounds reached but debater still has concerns (ensures symmetric
            defense-before-verdict), or "end" when debater is satisfied.
            """
            round_count = state.get("round_count", 1)
            debate_active = state.get("debate_active", True)

            if not debate_active:
                logger.info("Debater satisfied, ending debate")
                return "end"

            if round_count >= self.max_debate_rounds:
                logger.info(
                    "Max debate rounds reached, routing to final rebuttal",
                    rounds=round_count,
                )
                return "final_rebuttal"

            logger.info("Continuing debate", round=round_count + 1)
            return "continue"

        def after_main_agent(state: dict) -> str:
            """Route main_agent output to debate or verdict.

            After the initial research (round_count=1), always go to debate.
            After a final rebuttal (round_count >= max), go directly to verdict
            to preserve symmetry: defense always responds before verdict.
            """
            round_count = state.get("round_count", 0)
            if round_count >= self.max_debate_rounds:
                logger.info("Final rebuttal complete, proceeding to verdict")
                return "verdict"
            return "debate"

        # ── verdict_node ─────────────────────────────────────────────────
        async def verdict_node(state: dict, config: RunnableConfig) -> dict:
            """Synthesize debate into final verdict with verified facts.

            Merges all structured concerns and rebuttals into verified facts,
            injects them as a <system-reminder> JSON block, and generates
            a final Buy/Hold/Sell recommendation with conviction level.
            """
            report = state.get("research_report", "")
            round_count = state.get("round_count", 1)
            all_concerns = state.get("all_concerns", [])
            all_rebuttals = state.get("all_rebuttals", [])

            # Merge structured facts for evidence-based verdict
            concerns = [Concern(**c) for c in all_concerns] if all_concerns else []
            rebuttals = [Rebuttal(**r) for r in all_rebuttals] if all_rebuttals else []
            merged = merge_facts(concerns, rebuttals)
            verified_facts_block = (
                render_verified_facts_reminder(merged) if merged else ""
            )

            logger.info(
                "Starting verdict phase",
                round_count=round_count,
                concern_count=len(all_concerns),
                rebuttal_count=len(all_rebuttals),
                merged_fact_count=len(merged),
            )

            if emitter:
                _emit(emitter.synthesis_start())

            # Extract original research (before defense appendages)
            parts = report.split("\n\n## Defense (Round")
            original_research = parts[0].strip()

            verdict_prompt = f"""You are a Senior Investment Committee Judge delivering a final verdict.

{verified_facts_block}

## Research Report
{original_research[:6000]}

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
                # Empty — no new items; operator.add preserves accumulated state
                "all_concerns": [],
                "all_rebuttals": [],
            }

        # ── Graph Assembly ───────────────────────────────────────────────
        # Must use AnalysisState (not dict) so Annotated reducers are active.
        # operator.add on messages/all_concerns/all_rebuttals requires this.
        builder = StateGraph(AnalysisState)
        builder.add_node("main_agent", main_agent_node)

        if self.enable_debate:
            builder.add_node("debate", debate_node)
            builder.add_node("verdict", verdict_node)
            builder.add_edge(START, "main_agent")
            builder.add_conditional_edges(
                "main_agent",
                after_main_agent,
                {
                    "debate": "debate",  # Normal flow: research/rebuttal → debate
                    "verdict": "verdict",  # Final rebuttal complete → verdict
                },
            )
            builder.add_conditional_edges(
                "debate",
                should_continue,
                {
                    "continue": "main_agent",  # Rebuttal with evidence
                    "final_rebuttal": "main_agent",  # Last rebuttal before verdict
                    "end": "verdict",  # Debater satisfied, no concerns
                },
            )
            builder.add_edge("verdict", END)
        else:
            builder.add_edge(START, "main_agent")
            builder.add_edge("main_agent", END)

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
                subagent,
                prompt,
                config=config,
                emitter=emitter,
                on_event=on_event,
            )
            sa_duration = int((time.perf_counter() - sa_start) * 1000)

            if emitter and emit_fn:
                emit_fn(
                    emitter.subagent_result(
                        subagent_name=subagent_name,
                        status="success",
                        duration_ms=sa_duration,
                        result_summary=result,
                        tool_count=tool_count,
                    )
                )
            return result, tool_count

        except Exception as e:
            sa_duration = int((time.perf_counter() - sa_start) * 1000)
            if emitter and emit_fn:
                emit_fn(
                    emitter.subagent_result(
                        subagent_name=subagent_name,
                        status="error",
                        duration_ms=sa_duration,
                        result_summary=str(e),
                    )
                )
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
        analysis_cache = AnalysisToolCache()
        workflow = self._build_workflow(
            context, cache=analysis_cache, emitter=emitter, on_event=on_event
        )

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
            "all_concerns": [],
            "all_rebuttals": [],
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
            _safe_emit(
                emitter.deep_start(symbol, subagent_names, context.enable_debate)
            )

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
        finally:
            analysis_cache.log_stats()

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
