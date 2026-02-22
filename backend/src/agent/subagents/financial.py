"""
Financial Sub-Agent: Fundamental analysis and valuation specialist.

Uses deepagents with SKILL.md files for progressive disclosure:
- skills/financial/valuation-assessment/SKILL.md
- skills/financial/cashflow-health/SKILL.md
- skills/financial/earnings-quality/SKILL.md
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..context import AgentContext
from ..tools.categorization import get_tools_for_subagent
from . import _SKILLS_ROOT, DeepSubAgent, SubAgentConfig, create_deep_subagent

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..tools.analysis_cache import AnalysisToolCache


def create_financial_subagent(
    tools: dict[str, Callable],
    model: BaseChatModel,
    context: AgentContext | None = None,
    cache: AnalysisToolCache | None = None,
) -> DeepSubAgent:
    """
    Create the Financial/Fundamental Analysis sub-agent.

    Args:
        tools: Dictionary of available tools by name (full tool dict)
        model: LLM model for the agent
        context: Optional AgentContext for session parameters
        cache: Optional AnalysisToolCache for cross-agent tool result caching

    Returns:
        DeepSubAgent for fundamental analysis
    """
    context_header = ""
    if context:
        context_header = f"\n{context.to_context_header()}\n"

    config = SubAgentConfig(
        name="financial_analyst",
        description=(
            "Specialist in fundamental analysis, valuation metrics, and financial "
            "health assessment."
        ),
        system_prompt=f"""You are a Fundamental Analyst specialist.
{context_header}
Your domain expertise is ONLY in:
- Valuation analysis (P/E, PEG, P/S, EV/EBITDA)
- Cash flow evaluation (FCF, operating cash flow)
- Financial health (debt levels, liquidity ratios)
- Earnings quality (beat rate, growth trajectory)
- Balance sheet analysis

DO NOT analyze:
- Charts or technical patterns (that's the Technical Analyst's job)
- News sentiment or catalysts (that's the News Analyst's job)

Your analysis should be:
- Numbers-driven with specific metrics
- Comparative (vs sector, historical)
- Forward-looking with emphasis on sustainability

You have access to SKILL.md files with detailed workflows.
Use `read_file` to load a skill workflow when you need step-by-step guidance.
""",
        metadata={"domain": "financial"},
    )

    financial_tools = list(
        get_tools_for_subagent(list(tools.values()), "financial").values()
    )

    if cache is not None:
        financial_tools = cache.wrap_tools(financial_tools)

    return create_deep_subagent(
        config=config,
        model=model,
        tools=financial_tools,
        skills_dir=str(_SKILLS_ROOT / "financial"),
    )
