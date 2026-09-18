"""Deep ReAct agent with hierarchical research and adversarial debate."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from ..api.schemas.deep_agent_events import DeepEventEmitter, extract_risk_level
from ..core.utils.token_utils import extract_token_usage_from_messages
from .context import AgentContext
from .debate_types import VerdictAction
from .deep_research_context import DeepResearchContext
from .deep_workflow import AnalysisState, build_deep_workflow
from .llm_factory import get_llm
from .subagent_invoker import invoke_subagent
from .subagents.debater import create_debater_subagent
from .subagents.financial import create_financial_subagent
from .subagents.news import create_news_subagent
from .subagents.technical import create_technical_subagent
from .tools.analysis_cache import AnalysisToolCache
from .tools.categorization import get_all_tools_dict

logger = structlog.get_logger()

DEFAULT_MAX_DEBATE_ROUNDS = 2


class DeepReActAgent:
    """Orchestrate specialist sub-agents and an optional symmetric debate loop."""

    def __init__(
        self,
        settings: Any,
        tools: list[Any],
        enable_debate: bool = True,
        max_debate_rounds: int = DEFAULT_MAX_DEBATE_ROUNDS,
        order_repo: Any = None,
        data_manager: Any = None,
    ) -> None:
        self.settings = settings
        self.enable_debate = enable_debate
        self.max_debate_rounds = max_debate_rounds
        self._order_repo = order_repo
        self._data_manager = data_manager
        from ..services.evidence.context import install_tools

        install_tools(tools)
        self.tools_dict = get_all_tools_dict(tools)
        self.exa_api_key: str = getattr(settings, "exa_api_key", "")

        temperature = float(getattr(settings, "default_llm_temperature", 0.7))
        self.llm = get_llm("deep_planner", temperature=temperature, timeout=30)
        self.verdict_llm = get_llm("verdict", temperature=temperature, timeout=30)
        self._llm_technical = get_llm(
            "sub_technical",
            temperature=temperature,
            timeout=30,
        )
        self._llm_news = get_llm(
            "sub_news",
            temperature=temperature,
            timeout=30,
        )
        self._llm_financial = get_llm(
            "sub_financial",
            temperature=temperature,
            timeout=30,
        )
        self._llm_debater = get_llm(
            "sub_debater",
            temperature=temperature,
            timeout=30,
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
        return {
            "technical": create_technical_subagent(
                self.tools_dict,
                self._llm_technical,
                context,
                cache=cache,
            ),
            "news": create_news_subagent(
                self.tools_dict,
                self._llm_news,
                context,
                cache=cache,
            ),
            "financial": create_financial_subagent(
                self.tools_dict,
                self._llm_financial,
                context,
                cache=cache,
            ),
            "debater": create_debater_subagent(
                model=self._llm_debater,
                context=context,
                exa_api_key=self.exa_api_key,
            ),
        }

    def _build_workflow(
        self,
        context: AgentContext,
        cache: AnalysisToolCache,
        emitter: DeepEventEmitter | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> Any:
        """Build the graph; build_deep_workflow uses StateGraph(AnalysisState)."""
        return build_deep_workflow(
            self,
            context,
            cache,
            emitter=emitter,
            on_event=on_event,
        )

    async def _persist_verdict_decision(
        self,
        symbol: str,
        action: VerdictAction | None,
        *,
        chat_id: str,
        run_id: str,
        message_id: str,
        research_text: str = "",
        strategy: Any = None,
    ) -> None:
        """Persist Deep research as a non-actionable assessment, never a signal order."""
        if action not in {"BUY", "HOLD", "SELL", None}:
            raise ValueError(f"Unsupported structured verdict action: {action}")
        if self._order_repo is None:
            raise RuntimeError("Deep assessment storage is unavailable")
        from ..services.evidence.service import deep_summary

        evidence = await deep_summary(
            self._order_repo.collection.database, run_id, symbol, research_text
        )
        # A directional research stance is not a sized trading proposal.
        await self._order_repo.assess(
            request_key=run_id,
            run_id=run_id,
            source="deep",
            symbols=[symbol],
            proposals=[],
            research={symbol: research_text},
            evidence=evidence,
            strategy=strategy,
        )

    async def _invoke_subagent(
        self,
        subagent: Any,
        prompt: str,
        config: RunnableConfig | None = None,
        emitter: DeepEventEmitter | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[str, int]:
        result: tuple[str, int] = await invoke_subagent(
            subagent=subagent,
            prompt=prompt,
            config=config,
            emitter=emitter,
            on_event=on_event,
        )
        return result

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
        subagent_name = subagent.config.name
        if emitter and emit_fn:
            emit_fn(emitter.subagent_start(subagent_name, subagent.get_tool_names()))
        started = time.perf_counter()
        try:
            result, tool_count = await self._invoke_subagent(
                subagent,
                prompt,
                config=config,
                emitter=emitter,
                on_event=on_event,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            if emitter and emit_fn:
                emit_fn(
                    emitter.subagent_result(
                        subagent_name=subagent_name,
                        status="success",
                        duration_ms=duration_ms,
                        result_summary=result,
                        tool_count=tool_count,
                    )
                )
            return result, tool_count
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            if emitter and emit_fn:
                emit_fn(
                    emitter.subagent_result(
                        subagent_name=subagent_name,
                        status="error",
                        duration_ms=duration_ms,
                        result_summary=str(exc),
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
        research_context: DeepResearchContext | None = None,
    ) -> dict[str, Any]:
        context = AgentContext(
            symbol=symbol,
            user_id=user_id,
            risk_tolerance=(
                research_context.risk_tolerance
                if research_context and research_context.risk_tolerance
                else "moderate"
            ),
            investment_horizon=(
                research_context.investment_horizon if research_context else None
            ),
            enable_debate=(
                enable_debate if enable_debate is not None else self.enable_debate
            ),
        )
        emitter = DeepEventEmitter() if on_event else None
        analysis_cache = AnalysisToolCache()
        workflow = self._build_workflow(
            context,
            cache=analysis_cache,
            emitter=emitter,
            on_event=on_event,
        )
        config = RunnableConfig(
            configurable=context.to_dict(),
            tags=[f"symbol:{symbol}", f"user:{user_id}"],
            metadata={
                "agent_type": "DeepReActAgent",
                "analysis_type": context.analysis_type,
            },
        )
        initial_content = user_message or f"Analyze {symbol} comprehensively."
        research_context = research_context or DeepResearchContext.from_history(
            current_request=initial_content,
            conversation_history=[],
        )
        initial_state: AnalysisState = {
            "messages": [HumanMessage(content=initial_content)],
            "symbol": symbol,
            "round_count": 0,
            "research_report": "",
            "debate_active": context.enable_debate,
            "all_concerns": [],
            "all_rebuttals": [],
            "research_context": research_context.render(
                symbol=symbol,
                previous_report_char_limit=600,
            ),
            "research_context_with_report": research_context.render(symbol=symbol),
            "research_constraints": research_context.constraints,
            "prompt_versions": {},
        }

        def safe_emit(event: dict[str, Any]) -> None:
            if on_event is not None:
                try:
                    on_event(event)
                except Exception:
                    logger.warning(
                        "Failed to emit event",
                        event_type=event.get("type"),
                    )

        if emitter and on_event:
            safe_emit(
                emitter.deep_start(
                    symbol,
                    ["technical_analyst", "news_analyst", "financial_analyst"],
                    context.enable_debate,
                )
            )
        started = time.perf_counter()
        logger.info(
            "Starting analysis",
            symbol=symbol,
            session_id=context.session_id,
            current_date=context.current_date,
            enable_debate=context.enable_debate,
        )
        try:
            from ..services.evidence.service import run_deep

            raw_final_state = await run_deep(
                self, workflow, initial_state, config, symbol
            )
        except Exception as exc:
            logger.error(
                "Analysis failed",
                symbol=symbol,
                session_id=context.session_id,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            raise
        finally:
            analysis_cache.log_stats()

        final_state: dict[str, Any] = dict(raw_final_state)
        duration_ms = int((time.perf_counter() - started) * 1000)
        messages = final_state.get("messages", [])
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )
        final_state.update(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "agent_duration_ms": duration_ms,
            }
        )
        logger.info(
            "Analysis complete",
            symbol=symbol,
            session_id=context.session_id,
            total_rounds=final_state.get("round_count", 0),
            message_count=len(messages),
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )
        if emitter and on_event:
            report = final_state.get("research_report", "")
            verdict = final_state.get("verdict", {})
            safe_emit(
                emitter.verdict(
                    verdict_text=report,
                    risk_level=verdict.get("risk_level") or extract_risk_level(report),
                    tool_count=sum(
                        message.__class__.__name__ == "ToolMessage"
                        for message in messages
                    ),
                    total_duration_ms=duration_ms,
                )
            )
        return final_state
