"""
Localization utilities for language control in AI responses.

This module provides utilities for:
- Language code normalization
- Language instruction templates for AI prompts
- Helper functions for language parameter handling
"""

from typing import Literal

# Supported language codes
SupportedLanguage = Literal["zh-CN", "en"]

# Default language for the user-facing chat agent only (responds to the user
# in their locale).
DEFAULT_LANGUAGE: SupportedLanguage = "zh-CN"

# Invariant for the analysis pipeline (Phase 1 research, Phase 2 decisions,
# history summarization). Always English. Output is later translated by
# `translation_service.translate_batch` for zh-CN display. Locked to "en" so
# the English -> zh-CN translation direction is unambiguous and DashScope
# cannot reverse it.
ANALYSIS_OUTPUT_LANG: SupportedLanguage = "en"

# Language display names
LANGUAGE_NAMES: dict[str, str] = {
    "zh-CN": "简体中文",
    "en": "English",
}


def normalize_language_code(language: str | None) -> SupportedLanguage:
    """
    Normalize language code to supported format.

    Args:
        language: Raw language code from request (e.g., "zh-CN", "zh", "en-US", "en")

    Returns:
        Normalized language code ("zh-CN" or "en")
    """
    if not language:
        return DEFAULT_LANGUAGE

    # Normalize to lowercase for comparison
    lang_lower = language.lower().strip()

    # Map various Chinese codes to zh-CN
    if lang_lower in ("zh-cn", "zh", "zh-hans", "zh-sg", "chinese"):
        return "zh-CN"

    # Map various English codes to en
    if lang_lower in ("en", "en-us", "en-gb", "english"):
        return "en"

    # Default to Chinese for unknown codes
    return DEFAULT_LANGUAGE


def get_language_instruction(language: SupportedLanguage) -> str:
    """
    Get the language instruction to append to AI prompts.

    This instruction ensures the AI responds in the specified language
    regardless of the conversation history language.

    Args:
        language: Target language code

    Returns:
        Language instruction string to append to system prompt
    """
    if language == "zh-CN":
        return """

LANGUAGE REQUIREMENT:
You MUST respond in Simplified Chinese (简体中文).
- All explanations, analysis, and recommendations must be in Chinese
- Technical terms can include English in parentheses for clarity (e.g., 市盈率 (P/E Ratio))
- Numbers, stock symbols, and dates can remain in standard format
- Regardless of conversation history language, your output MUST be in Chinese
"""
    else:  # English
        return """

LANGUAGE REQUIREMENT:
You MUST respond in English.
- All explanations, analysis, and recommendations must be in English
- Use clear, professional financial terminology
- Regardless of conversation history language, your output MUST be in English
"""


def get_brief_language_instruction(language: SupportedLanguage) -> str:
    """
    Get a brief language instruction for shorter prompts.

    Args:
        language: Target language code

    Returns:
        Brief language instruction string
    """
    if language == "zh-CN":
        return "IMPORTANT: Respond in Simplified Chinese (简体中文)."
    else:
        return "IMPORTANT: Respond in English."


def get_language_name(language: SupportedLanguage) -> str:
    """
    Get the display name for a language code.

    Args:
        language: Language code

    Returns:
        Display name of the language
    """
    return LANGUAGE_NAMES.get(language, LANGUAGE_NAMES[DEFAULT_LANGUAGE])


# Tool display name translations
TOOL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    "search_ticker": {
        "zh-CN": "搜索股票代码",
        "en": "Search Ticker",
    },
    "get_company_overview": {
        "zh-CN": "公司概览",
        "en": "Company Overview",
    },
    "get_news_sentiment": {
        "zh-CN": "新闻情绪分析",
        "en": "News Sentiment",
    },
    "get_financial_statements": {
        "zh-CN": "财务报表",
        "en": "Financial Statements",
    },
    "get_market_movers": {
        "zh-CN": "市场动向",
        "en": "Market Movers",
    },
    "fibonacci_analysis_tool": {
        "zh-CN": "斐波那契分析",
        "en": "Fibonacci Analysis",
    },
    "stochastic_analysis_tool": {
        "zh-CN": "随机指标分析",
        "en": "Stochastic Analysis",
    },
    "get_historical_prices": {
        "zh-CN": "历史价格查询",
        "en": "Historical Prices",
    },
    "get_stock_price": {
        "zh-CN": "获取股票价格",
        "en": "Get Stock Price",
    },
    "get_earnings": {
        "zh-CN": "获取盈利数据",
        "en": "Get Earnings",
    },
    "get_cash_flow": {
        "zh-CN": "获取现金流",
        "en": "Get Cash Flow",
    },
    "get_balance_sheet": {
        "zh-CN": "获取资产负债表",
        "en": "Get Balance Sheet",
    },
}


def get_tool_display_name(
    tool_name: str, language: SupportedLanguage = DEFAULT_LANGUAGE
) -> str:
    """
    Get the localized display name for a tool.

    Args:
        tool_name: Internal tool name (e.g., "get_company_overview")
        language: Target language code

    Returns:
        Localized display name for the tool
    """
    if tool_name in TOOL_DISPLAY_NAMES:
        return TOOL_DISPLAY_NAMES[tool_name].get(
            language,
            TOOL_DISPLAY_NAMES[tool_name].get(
                "en", tool_name.replace("_", " ").title()
            ),
        )
    # Default: convert snake_case to Title Case
    return tool_name.replace("_", " ").title()
