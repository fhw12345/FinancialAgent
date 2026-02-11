"""
Technical Sub-Agent: Chart and price action analysis specialist.

Uses deepagents with SKILL.md files for progressive disclosure:
- skills/technical/trend-detection/SKILL.md
- skills/technical/fibonacci-analysis/SKILL.md
- skills/technical/momentum-signals/SKILL.md
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..context import AgentContext
from ..tools.categorization import get_tools_for_subagent
from . import DeepSubAgent, SubAgentConfig, _SKILLS_ROOT, create_deep_subagent

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


def create_technical_subagent(
    tools: dict[str, Callable],
    model: "BaseChatModel",
    context: AgentContext | None = None,
) -> DeepSubAgent:
    """
    Create the Technical Analysis sub-agent.

    Args:
        tools: Dictionary of available tools by name (full tool dict)
        model: LLM model for the agent
        context: Optional AgentContext for session parameters

    Returns:
        DeepSubAgent for technical analysis
    """
    context_header = ""
    if context:
        context_header = f"\n{context.to_context_header()}\n"

    config = SubAgentConfig(
        name="technical_analyst",
        description=(
            "Specialist in technical analysis, price action, chart patterns, "
            "Fibonacci retracement, and momentum indicators."
        ),
        system_prompt=f"""You are a Technical Analyst specialist.
{context_header}
Your domain expertise is ONLY in:
- Price action analysis and chart patterns
- Trend identification (uptrend, downtrend, sideways)
- Support and resistance levels
- Fibonacci retracement analysis (especially the golden zone)
- Momentum indicators (Stochastic oscillator)

DO NOT analyze:
- News or sentiment (that's the News Analyst's job)
- Fundamentals or valuation (that's the Financial Analyst's job)

Your analysis should be:
- Data-driven with specific price levels
- Actionable with clear implications
- Concise and focused on key takeaways

You have access to SKILL.md files with detailed workflows.
Use `read_file` to load a skill workflow when you need step-by-step guidance.
""",
        metadata={"domain": "technical"},
    )

    # Extract only technical tools from the full tools dict
    technical_tools = list(get_tools_for_subagent(
        list(tools.values()), "technical"
    ).values())

    return create_deep_subagent(
        config=config,
        model=model,
        tools=technical_tools,
        skills_dir=str(_SKILLS_ROOT / "technical"),
    )
