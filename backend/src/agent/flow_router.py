"""Hybrid router for selecting the chat execution flow."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from langchain_core.messages import HumanMessage

from ..core.utils import message_content_to_text
from .llm_factory import get_llm

logger = structlog.get_logger()

AgentFlow = Literal["v2", "v3", "v4-deep"]
AgentVersion = Literal["auto", "v2", "v3", "v4-deep"]
RouteSource = Literal["explicit", "rule", "classifier", "fallback"]

DEEP_MARKERS = (
    "deep analysis",
    "deep dive",
    "comprehensive investment analysis",
    "full investment analysis",
    "investment committee",
    "bull case",
    "bear case",
    "adversarial review",
    "debate",
    "investment thesis",
    "深度分析",
    "深入分析",
    "全面投资分析",
    "完整投资分析",
    "完整研究",
    "投资委员会",
    "多空辩论",
    "反方质疑",
    "投资逻辑",
)

TOOL_MARKERS = (
    "current price",
    "latest price",
    "stock price",
    "quote",
    "market movers",
    "latest news",
    "recent news",
    "earnings",
    "revenue",
    "cash flow",
    "balance sheet",
    "valuation",
    "p/e",
    "pe ratio",
    "technical analysis",
    "fibonacci",
    "stochastic",
    "rsi",
    "macd",
    "support",
    "resistance",
    "options",
    "put call",
    "insider",
    "当前价格",
    "最新价格",
    "股价",
    "行情",
    "市场动向",
    "最新新闻",
    "近期新闻",
    "财报",
    "营收",
    "现金流",
    "资产负债表",
    "估值",
    "市盈率",
    "技术分析",
    "斐波那契",
    "随机指标",
    "支撑位",
    "阻力位",
    "期权",
    "看涨看跌比",
    "内部交易",
)

CONCEPT_MARKERS = (
    "what is",
    "explain",
    "define",
    "difference between",
    "how does",
    "summarize",
    "什么是",
    "解释",
    "定义",
    "概念",
    "区别",
    "原理",
    "总结",
)

LIVE_INTENT_MARKERS = (
    "current",
    "latest",
    "today",
    "recent",
    "right now",
    "analyze",
    "analysis",
    "compare",
    "show me",
    "get ",
    "当前",
    "最新",
    "今天",
    "近期",
    "现在",
    "分析",
    "比较",
    "查看",
    "查询",
    "给我",
)

SYMBOL_ACTION_MARKERS = (
    "analyze",
    "outlook",
    "trend",
    "risk",
    "target price",
    "buy",
    "sell",
    "hold",
    "this stock",
    "this company",
    "it",
    "分析",
    "走势",
    "怎么看",
    "前景",
    "风险",
    "目标价",
    "值得买吗",
    "这只股票",
    "这家公司",
    "它",
)

FINANCIAL_CONTEXT_MARKERS = (
    TOOL_MARKERS
    + SYMBOL_ACTION_MARKERS
    + (
        "stock",
        "company",
        "portfolio",
        "股票",
        "公司",
        "投资组合",
    )
)

TICKER_RE = re.compile(r"\b[A-Z]{2,5}(?:[.-][A-Z])?\b")
TICKER_STOP_WORDS = {"AI", "US", "CEO", "CFO", "ETF", "IPO", "GDP", "CPI"}


@dataclass(frozen=True)
class FlowRoutingDecision:
    """Selected execution flow with stable diagnostics."""

    flow: AgentFlow
    source: RouteSource
    reason_code: str

    def as_event(self) -> dict[str, str]:
        return {
            "type": "route_selected",
            "flow": self.flow,
            "source": self.source,
            "reason_code": self.reason_code,
        }

    def as_metadata(self) -> dict[str, str]:
        return self.as_event()


class AgentFlowRouter:
    """Rule-first router with an LLM classifier for ambiguous requests."""

    def __init__(self, llm: Any | None = None) -> None:
        self._llm = llm

    async def select(
        self,
        *,
        message: str,
        current_symbol: str | None,
        requested_version: AgentVersion,
    ) -> FlowRoutingDecision:
        """Select v2, v3, or v4-deep for one user turn."""
        if requested_version != "auto":
            return FlowRoutingDecision(
                flow=requested_version,
                source="explicit",
                reason_code="explicit_override",
            )

        rule_decision = self._apply_rules(message, current_symbol)
        if rule_decision is not None:
            return rule_decision

        return await self._classify(message, current_symbol)

    def _apply_rules(
        self,
        message: str,
        current_symbol: str | None,
    ) -> FlowRoutingDecision | None:
        text = message.strip()
        lowered = text.lower()
        explicit_ticker = any(
            ticker not in TICKER_STOP_WORDS for ticker in TICKER_RE.findall(text)
        )
        has_financial_context = (
            explicit_ticker
            or any(marker in lowered for marker in FINANCIAL_CONTEXT_MARKERS)
            or (
                current_symbol is not None
                and any(marker in lowered for marker in SYMBOL_ACTION_MARKERS)
            )
        )

        if any(marker in lowered for marker in DEEP_MARKERS) and has_financial_context:
            return FlowRoutingDecision(
                flow="v4-deep",
                source="rule",
                reason_code="deep_financial_request",
            )

        if any(marker in lowered for marker in CONCEPT_MARKERS) and not any(
            marker in lowered for marker in LIVE_INTENT_MARKERS
        ):
            return FlowRoutingDecision(
                flow="v2",
                source="rule",
                reason_code="concept_explanation",
            )

        if any(marker in lowered for marker in TOOL_MARKERS):
            return FlowRoutingDecision(
                flow="v3",
                source="rule",
                reason_code="live_data_or_tool_request",
            )

        if current_symbol and any(
            marker in lowered for marker in SYMBOL_ACTION_MARKERS
        ):
            return FlowRoutingDecision(
                flow="v3",
                source="rule",
                reason_code="selected_symbol_analysis",
            )

        if explicit_ticker and any(
            marker in lowered for marker in SYMBOL_ACTION_MARKERS
        ):
            return FlowRoutingDecision(
                flow="v3",
                source="rule",
                reason_code="explicit_symbol_analysis",
            )

        return None

    async def _classify(
        self,
        message: str,
        current_symbol: str | None,
    ) -> FlowRoutingDecision:
        llm = self._llm or get_llm(
            "router",
            temperature=0,
            max_tokens=80,
            timeout=15,
        )
        prompt = f"""Classify this Financial Agent request into exactly one flow.

v2: direct conversational answer; no current market data or tools needed.
v3: tool-using financial analysis, current data, news, fundamentals, or technical analysis.
v4-deep: explicitly requests comprehensive/deep investment research, multi-angle analysis, or adversarial debate.

Selected symbol from UI: {current_symbol or "none"}
User message: {message[:2000]}

Return JSON only: {{"flow":"v2"|"v3"|"v4-deep"}}"""

        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            text = message_content_to_text(response.content)
            payload = self._extract_json(text)
            flow = payload.get("flow")
            if flow not in ("v2", "v3", "v4-deep"):
                raise ValueError(f"Invalid flow: {flow!r}")
            return FlowRoutingDecision(
                flow=flow,
                source="classifier",
                reason_code=f"classifier_{flow.replace('-', '_')}",
            )
        except Exception as exc:
            logger.warning(
                "flow_router_classifier_failed",
                error=str(exc),
                fallback_flow="v3",
                message_preview=message[:120],
            )
            return FlowRoutingDecision(
                flow="v3",
                source="fallback",
                reason_code="classifier_error_fallback",
            )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        stripped = text.strip().removeprefix("```json").removeprefix("```")
        stripped = stripped.removesuffix("```").strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Classifier did not return a JSON object")
        parsed = json.loads(stripped[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("Classifier JSON must be an object")
        return parsed
