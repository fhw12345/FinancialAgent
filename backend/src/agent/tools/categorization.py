"""
Tool Categorization Module.

Provides utilities for categorizing tools by domain/specialist,
enabling the hierarchical agent architecture where each sub-agent
has access to a specific subset of tools.

Categories:
- technical: Fibonacci, Stochastic, Historical Prices
- news: News search, Market movers, Sentiment
- financial: Company overview, Financials, Earnings, Insider activity
- insights: Market insights categories and metrics
"""

from collections.abc import Callable

# Tool name to category mapping
TOOL_CATEGORIES: dict[str, str] = {
    # Technical Analysis Tools
    "fibonacci_analysis_tool": "technical",
    "stochastic_analysis_tool": "technical",
    "get_historical_prices": "technical",
    # News/Sentiment Tools
    "get_news_sentiment": "news",
    "get_market_movers": "news",
    # Financial/Fundamental Tools
    "get_company_overview": "financial",
    "get_financial_statements": "financial",
    "get_company_earnings": "financial",
    "get_insider_activity": "financial",
    "get_etf_holdings": "financial",
    "search_ticker": "financial",
    # Market Insights Tools
    "list_insight_categories": "insights",
    "get_insight_category": "insights",
    "get_insight_metric": "insights",
    "get_insight_trend": "insights",
    # Options Tools
    "get_put_call_ratio": "options",
    # Commodities Tools
    "get_copper_commodity": "commodities",
}


def categorize_tools(tools: list[Callable]) -> dict[str, list[Callable]]:
    """
    Categorize a list of tools by domain.

    Args:
        tools: List of tool functions (decorated with @tool)

    Returns:
        Dictionary mapping category names to lists of tools
    """
    categories: dict[str, list[Callable]] = {
        "technical": [],
        "news": [],
        "financial": [],
        "insights": [],
        "options": [],
        "commodities": [],
        "other": [],
    }

    for tool in tools:
        tool_name = getattr(tool, "name", str(tool))
        category = TOOL_CATEGORIES.get(tool_name, "other")
        categories[category].append(tool)

    return categories


def tools_to_dict(tools: list[Callable]) -> dict[str, Callable]:
    """
    Convert a list of tools to a dictionary keyed by tool name.

    Args:
        tools: List of tool functions

    Returns:
        Dictionary mapping tool names to tool functions
    """
    return {getattr(tool, "name", str(tool)): tool for tool in tools}


def get_tools_for_subagent(
    tools: list[Callable],
    subagent_type: str,
) -> dict[str, Callable]:
    """
    Get the subset of tools appropriate for a specific sub-agent type.

    Args:
        tools: Full list of available tools
        subagent_type: Type of sub-agent (technical, news, financial, debater)

    Returns:
        Dictionary of tool name -> tool function for that sub-agent
    """
    categorized = categorize_tools(tools)

    # Map sub-agent types to categories they can use
    subagent_categories: dict[str, list[str]] = {
        "technical": ["technical"],
        "news": ["news"],
        "financial": ["financial", "insights"],
        "debater": ["news", "financial", "options"],  # Debater can use multiple
    }

    allowed_categories = subagent_categories.get(subagent_type, [])

    result: dict[str, Callable] = {}
    for category in allowed_categories:
        for tool in categorized.get(category, []):
            tool_name = getattr(tool, "name", str(tool))
            result[tool_name] = tool

    return result


def get_all_tools_dict(tools: list[Callable]) -> dict[str, Callable]:
    """
    Get all tools as a dictionary for skill creation.

    This is the format expected by skill creation functions.

    Args:
        tools: Full list of available tools

    Returns:
        Dictionary of tool name -> tool function
    """
    return tools_to_dict(tools)


def log_tool_categories(tools: list[Callable]) -> dict[str, int]:
    """
    Get tool counts by category for logging.

    Args:
        tools: List of tools to categorize

    Returns:
        Dictionary of category -> count
    """
    categorized = categorize_tools(tools)
    return {cat: len(tool_list) for cat, tool_list in categorized.items() if tool_list}
