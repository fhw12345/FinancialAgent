"""
News Sub-Agent: Sentiment and market mood analysis specialist.

Uses deepagents with SKILL.md files for progressive disclosure:
- skills/news/sentiment-analysis/SKILL.md
- skills/news/catalyst-identification/SKILL.md
- skills/news/market-mood/SKILL.md
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..context import AgentContext
from ..tools.categorization import get_tools_for_subagent
from . import _SKILLS_ROOT, DeepSubAgent, SubAgentConfig, create_deep_subagent

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


def create_news_subagent(
    tools: dict[str, Callable],
    model: "BaseChatModel",
    context: AgentContext | None = None,
) -> DeepSubAgent:
    """
    Create the News/Sentiment Analysis sub-agent.

    Args:
        tools: Dictionary of available tools by name (full tool dict)
        model: LLM model for the agent
        context: Optional AgentContext for session parameters

    Returns:
        DeepSubAgent for news/sentiment analysis
    """
    context_header = ""
    if context:
        context_header = f"\n{context.to_context_header()}\n"

    config = SubAgentConfig(
        name="news_analyst",
        description=(
            "Specialist in news sentiment analysis, market drivers, and catalyst "
            "identification."
        ),
        system_prompt=f"""You are a News and Sentiment Analyst specialist.
{context_header}
Your domain expertise is ONLY in:
- News sentiment analysis and aggregation
- Catalyst identification (earnings, product launches, events)
- Market mood assessment (risk-on vs risk-off)
- Sector performance and trends
- Qualitative factors affecting stock prices

DO NOT analyze:
- Charts or technical patterns (that's the Technical Analyst's job)
- Financial statements or valuation (that's the Financial Analyst's job)

Your analysis should be:
- Timely with focus on recent developments
- Balanced showing both positive and negative news
- Contextual within broader market environment

You have access to SKILL.md files with detailed workflows.
Use `read_file` to load a skill workflow when you need step-by-step guidance.
""",
        metadata={"domain": "news"},
    )

    news_tools = list(get_tools_for_subagent(list(tools.values()), "news").values())

    return create_deep_subagent(
        config=config,
        model=model,
        tools=news_tools,
        skills_dir=str(_SKILLS_ROOT / "news"),
    )
