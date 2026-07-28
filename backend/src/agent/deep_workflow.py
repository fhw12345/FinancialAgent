"""LangGraph workflow construction for the Deep ReAct agent."""

from __future__ import annotations

import operator
import time
from collections.abc import Callable
from typing import Annotated, Any, TypedDict

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from ..api.schemas.deep_agent_events import DeepEventEmitter
from .context import AgentContext
from .debate_types import (
    Concern,
    DeepVerdict,
    Rebuttal,
    merge_facts,
    namespace_concern_ids,
    parse_debater_output,
    parse_rebuttal_output,
    render_verified_facts_reminder,
    validate_rebuttal_coverage,
    validate_verdict_assessments,
)
from .prompt_registry import PromptSpec, get_prompt, render_prompt
from .subagents.debater import TERMINATION_SIGNAL
from .tools.analysis_cache import AnalysisToolCache

logger = structlog.get_logger()


class AnalysisState(TypedDict, total=False):
    """State shared by Deep research, debate, rebuttal, and verdict nodes."""

    messages: Annotated[list[BaseMessage], operator.add]
    symbol: str
    round_count: int
    research_report: str
    debate_active: bool
    all_concerns: Annotated[list[dict[str, Any]], operator.add]
    all_rebuttals: Annotated[list[dict[str, Any]], operator.add]
    research_context: str
    research_context_with_report: str
    research_constraints: tuple[str, ...]
    prompt_versions: dict[str, str]
    verdict: dict[str, Any]


def build_deep_workflow(
    agent: Any,
    context: AgentContext,
    cache: AnalysisToolCache,
    emitter: DeepEventEmitter | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> Any:
    """Build the symmetric Deep debate graph using StateGraph(AnalysisState)."""
    subagents = agent._create_subagents(context, cache=cache)

    def emit(event: dict[str, Any]) -> None:
        if on_event is not None:
            try:
                on_event(event)
            except Exception:
                logger.warning("Failed to emit event", event_type=event.get("type"))

    def constrained_subagent(state: AnalysisState, default: str) -> str:
        constraints = set(state.get("research_constraints", ()))
        if "technical_focus" in constraints:
            return "technical"
        if {"valuation_focus", "fundamental_focus", "exclude_news"} & constraints:
            return "financial"
        return default

    def record_prompt(prompt_id: str) -> PromptSpec:
        spec = get_prompt(prompt_id)
        emit(
            {
                "type": "prompt_used",
                "prompt_id": spec.prompt_id,
                "version": spec.versioned_id,
            }
        )
        return spec

    async def main_agent_node(
        state: AnalysisState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        symbol = state.get("symbol", context.symbol)
        round_count = state.get("round_count", 0)
        configurable = config.get("configurable", {})

        if round_count == 0:
            logger.info(
                "Starting research phase",
                symbol=symbol,
                session_id=configurable.get("session_id"),
                current_date=configurable.get("current_date"),
            )
            shared_context = state.get("research_context", "")
            constraints = set(state.get("research_constraints", ()))
            allowed = {"technical", "news", "financial"}
            if "technical_focus" in constraints:
                allowed = {"technical"}
            elif {"valuation_focus", "fundamental_focus"} & constraints:
                allowed = {"financial"}
            if "exclude_news" in constraints:
                allowed.discard("news")

            tasks = [
                (
                    "technical",
                    f"{shared_context}\n\nAnalyze the technical setup for {symbol} "
                    "in direct response to the current request above. Focus on "
                    "trend, Fibonacci levels, and momentum.",
                ),
                (
                    "news",
                    f"{shared_context}\n\nAnalyze recent news and sentiment for "
                    f"{symbol} in direct response to the current request above. "
                    "Include catalyst assessment and market mood.",
                ),
                (
                    "financial",
                    f"{shared_context}\n\nAnalyze the fundamentals of {symbol} "
                    "in direct response to the current request above. Focus on "
                    "valuation, cash flow health, and earnings quality.",
                ),
            ]
            reports: dict[str, str] = {}
            for subagent_key, prompt in tasks:
                if subagent_key not in allowed:
                    continue
                report, _ = await agent._invoke_with_events(
                    subagents[subagent_key],
                    prompt,
                    config=config,
                    emitter=emitter,
                    on_event=on_event,
                    emit_fn=emit,
                )
                reports[subagent_key] = report

            if emitter and not context.enable_debate:
                emit(emitter.synthesis_start())
            sections = [
                (key, title)
                for key, title in (
                    ("technical", "Technical Analysis"),
                    ("news", "News & Sentiment Analysis"),
                    ("financial", "Fundamental Analysis"),
                )
                if key in reports
            ]
            combined_report = "\n\n".join(
                f"## {title}\n{reports[key]}" for key, title in sections
            )
            logger.info(
                "Research phase complete",
                symbol=symbol,
                report_length=len(combined_report),
            )
            return {
                "messages": [AIMessage(content=combined_report, name="Researcher")],
                "research_report": combined_report,
                "round_count": round_count,
                "all_concerns": [],
                "all_rebuttals": [],
            }

        all_concerns = state.get("all_concerns", [])
        logger.info(
            "Starting rebuttal phase",
            round=round_count,
            concern_count=len(all_concerns),
        )
        if emitter:
            emit(emitter.rebuttal_start(round_count))
        started = time.perf_counter()
        concern_models = [Concern(**item) for item in all_concerns]
        concern_lines = "\n".join(
            f"- [{concern.severity}] {concern.id}: "
            f"{concern.claim} — {concern.challenge}"
            for concern in concern_models
        )
        spec = record_prompt("deep-rebuttal")
        prompt = render_prompt(
            "deep-rebuttal",
            research_context=state.get("research_context_with_report", ""),
            symbol=symbol,
            concern_lines=concern_lines,
        )
        subagent_key = constrained_subagent(state, "financial")
        defense, tool_count = await agent._invoke_with_events(
            subagents[subagent_key],
            prompt,
            config=config,
            emitter=emitter,
            on_event=on_event,
            emit_fn=emit,
            raise_on_error=False,
        )
        output = parse_rebuttal_output(defense)
        validate_rebuttal_coverage(output.rebuttals, concern_models)
        rebuttals = [item.model_dump() for item in output.rebuttals]
        duration_ms = int((time.perf_counter() - started) * 1000)
        if emitter:
            emit(
                emitter.rebuttal_result(
                    current_round=round_count,
                    defense_summary=defense,
                    tool_count=tool_count,
                    duration_ms=duration_ms,
                    rebuttals=rebuttals,
                )
            )
        updated_report = (
            f"{state.get('research_report', '')}"
            f"\n\n## Defense (Round {round_count})\n{defense}"
        )
        logger.info(
            "Rebuttal phase complete",
            round=round_count,
            tool_count=tool_count,
            parsed_rebuttals=len(rebuttals),
            duration_ms=duration_ms,
        )
        return {
            "messages": [AIMessage(content=defense, name="Defender")],
            "research_report": updated_report,
            "round_count": round_count,
            "all_concerns": [],
            "all_rebuttals": rebuttals,
            "prompt_versions": {
                **state.get("prompt_versions", {}),
                spec.prompt_id: spec.versioned_id,
            },
        }

    async def debate_node(
        state: AnalysisState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        report = state.get("research_report", "")
        round_count = state.get("round_count", 0)
        logger.info(
            "Starting debate phase",
            round=round_count + 1,
            session_id=config.get("configurable", {}).get("session_id"),
        )
        if emitter:
            emit(emitter.debate_start(round_count + 1, agent.max_debate_rounds))

        truncated_report = report[:3000]
        if len(report) > 3000:
            last_period = truncated_report.rfind(".")
            if last_period > 1500:
                truncated_report = truncated_report[: last_period + 1]
        spec = record_prompt("deep-debater")
        prompt = render_prompt(
            "deep-debater",
            research_context=state.get("research_context_with_report", ""),
            report=truncated_report,
            termination_signal=TERMINATION_SIGNAL,
        )
        subagent_key = constrained_subagent(state, "debater")
        critique, _ = await agent._invoke_with_events(
            subagents[subagent_key],
            prompt,
            config=config,
            emitter=emitter,
            on_event=on_event,
            emit_fn=emit,
        )
        new_round = round_count + 1
        output = parse_debater_output(critique)
        namespaced_concerns = namespace_concern_ids(
            output.concerns,
            round_number=new_round,
        )
        concerns = [item.model_dump() for item in namespaced_concerns]
        has_concerns = not output.terminated and bool(concerns)
        logger.info(
            "Debate round complete",
            round=new_round,
            has_concerns=has_concerns,
            parsed_concerns=len(concerns),
            terminated=output.terminated,
        )
        if emitter:
            emit(emitter.debate_round(new_round, has_concerns, critique, concerns))
        return {
            "messages": [AIMessage(content=critique, name="Debater")],
            "round_count": new_round,
            "research_report": report,
            "all_concerns": concerns,
            "all_rebuttals": [],
            "debate_active": has_concerns,
            "prompt_versions": {
                **state.get("prompt_versions", {}),
                spec.prompt_id: spec.versioned_id,
            },
        }

    def should_continue(state: AnalysisState) -> str:
        if not state.get("debate_active", True):
            logger.info("Debater satisfied, ending debate")
            return "end"
        round_count = state.get("round_count", 1)
        if round_count >= agent.max_debate_rounds:
            logger.info(
                "Max debate rounds reached, routing to final rebuttal",
                rounds=round_count,
            )
            return "final_rebuttal"
        logger.info("Continuing debate", round=round_count + 1)
        return "continue"

    def after_main_agent(state: AnalysisState) -> str:
        if state.get("round_count", 0) >= agent.max_debate_rounds:
            logger.info("Final rebuttal complete, proceeding to verdict")
            return "verdict"
        return "debate"

    async def verdict_node(
        state: AnalysisState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        report = state.get("research_report", "")
        round_count = state.get("round_count", 1)
        concerns = [Concern(**item) for item in state.get("all_concerns", [])]
        rebuttals = [Rebuttal(**item) for item in state.get("all_rebuttals", [])]
        merged = merge_facts(concerns, rebuttals)
        verified_facts = render_verified_facts_reminder(merged) if merged else ""
        logger.info(
            "Starting verdict phase",
            round_count=round_count,
            concern_count=len(concerns),
            rebuttal_count=len(rebuttals),
            merged_fact_count=len(merged),
        )
        if emitter:
            emit(emitter.synthesis_start())
        original_research = report.split("\n\n## Defense (Round")[0].strip()
        spec = record_prompt("deep-verdict")
        prompt = render_prompt(
            "deep-verdict",
            verified_facts=verified_facts,
            research_context=state.get("research_context_with_report", ""),
            report=original_research[:6000],
        )
        structured_llm = agent.verdict_llm.with_structured_output(DeepVerdict)
        raw_verdict = await structured_llm.ainvoke(
            [HumanMessage(content=prompt)],
            config=config,
        )
        verdict = (
            raw_verdict
            if isinstance(raw_verdict, DeepVerdict)
            else DeepVerdict.model_validate(raw_verdict, strict=True)
        )
        validate_verdict_assessments(verdict, concerns)
        logger.info(
            "Verdict phase complete",
            verdict_length=len(verdict.report_markdown),
            action=verdict.action,
        )
        return {
            "messages": [
                AIMessage(content=verdict.report_markdown, name="Judge"),
            ],
            "research_report": verdict.report_markdown,
            "round_count": round_count,
            "all_concerns": [],
            "all_rebuttals": [],
            "verdict": verdict.model_dump(),
            "prompt_versions": {
                **state.get("prompt_versions", {}),
                spec.prompt_id: spec.versioned_id,
            },
        }

    builder = StateGraph(AnalysisState)
    builder.add_node("main_agent", main_agent_node)
    builder.add_edge(START, "main_agent")
    if context.enable_debate:
        builder.add_node("debate", debate_node)
        builder.add_node("verdict", verdict_node)
        builder.add_conditional_edges(
            "main_agent",
            after_main_agent,
            {"debate": "debate", "verdict": "verdict"},
        )
        builder.add_conditional_edges(
            "debate",
            should_continue,
            {
                "continue": "main_agent",
                "final_rebuttal": "main_agent",
                "end": "verdict",
            },
        )
        builder.add_edge("verdict", END)
    else:
        builder.add_edge("main_agent", END)
    return builder.compile()
