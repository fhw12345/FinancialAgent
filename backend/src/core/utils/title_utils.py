"""
Chat title generation utilities.

Provides functions for generating meaningful chat titles from conversation content.
Used to replace default "New Chat" titles with context-aware titles like "AAPL Analysis".
"""

import re
from typing import Any

import structlog

from .message_content import message_content_to_text

logger = structlog.get_logger()

# Stock symbols pattern: 1-5 uppercase letters
SYMBOL_PATTERN = re.compile(r"\b[A-Z]{1,5}\b")

# LLM-generated title pattern: [chat_title: Title Here]
CHAT_TITLE_PATTERN = re.compile(r"\[chat_title:\s*(.+?)\]\s*$", re.IGNORECASE)

# Common words that look like symbols but aren't
STOP_WORDS = frozenset(
    {
        "I",
        "A",
        "THE",
        "AND",
        "OR",
        "FOR",
        "TO",
        "IN",
        "ON",
        "AT",
        "OF",
        "IS",
        "IT",
        "MY",
        "AN",
        "AS",
        "BE",
        "BY",
        "DO",
        "GO",
        "HE",
        "IF",
        "ME",
        "NO",
        "SO",
        "UP",
        "WE",
        "ALL",
        "CAN",
        "GET",
        "HAS",
        "HOW",
        "ITS",
        "LET",
        "NEW",
        "NOW",
        "OLD",
        "OUR",
        "OUT",
        "OWN",
        "SAY",
        "SHE",
        "TOO",
        "TWO",
        "USE",
        "WAY",
        "WHO",
        "WHY",
        "YOU",
        "ARE",
        "BUT",
        "ETF",
        "IPO",
        "CEO",
        "CFO",
        "SEC",
        "NYSE",
        "USD",
        "EUR",
        "GBP",
        "JPY",
        "CNY",
        "HKD",
    }
)

# Action keywords mapped to title suffixes
ACTION_KEYWORDS: dict[str, list[str]] = {
    "Technical Analysis": [
        "sma",
        "ema",
        "rsi",
        "macd",
        "stoch",
        "bollinger",
        "bbands",
        "indicator",
        "technical",
        "chart",
        "trend",
        "momentum",
        "support",
        "resistance",
    ],
    "Fundamental Analysis": [
        "earnings",
        "revenue",
        "profit",
        "margin",
        "p/e",
        "pe ratio",
        "eps",
        "fundamental",
        "valuation",
        "growth",
    ],
    "Cash Flow": [
        "cash flow",
        "cashflow",
        "fcf",
        "free cash",
        "operating cash",
        "capex",
    ],
    "Balance Sheet": [
        "balance sheet",
        "assets",
        "liabilities",
        "equity",
        "debt",
        "current ratio",
    ],
    "News": [
        "news",
        "headlines",
        "article",
        "sentiment",
        "media",
        "announcement",
    ],
    "Price": [
        "price",
        "quote",
        "stock price",
        "current price",
        "how much",
        "trading at",
    ],
    "Insider Activity": ["insider", "executive", "buy", "sell", "transaction"],
    "ETF Holdings": ["etf", "holdings", "fund", "composition", "allocation"],
    "Market Movers": ["movers", "gainers", "losers", "most active", "top stocks"],
    "Comparison": ["compare", "versus", "vs", "difference", "better"],
    "Portfolio": ["portfolio", "holdings", "positions", "watchlist"],
}

# Maximum title length
MAX_TITLE_LENGTH = 50
GENERIC_CHAT_TITLES = frozenset(
    {
        "new chat",
        "chat analysis",
        "analysis",
        "stock analysis",
        "general chat",
    }
)


def is_generic_chat_title(title: str | None) -> bool:
    """Return whether a title is a placeholder that may be safely replaced."""
    return not title or title.strip().casefold() in GENERIC_CHAT_TITLES


def extract_symbols(text: str) -> list[str]:
    """
    Extract likely stock symbols from text.

    Args:
        text: Text to extract symbols from

    Returns:
        List of unique symbols found (deduplicated, ordered by first occurrence)

    Examples:
        >>> extract_symbols("What's the price of AAPL?")
        ['AAPL']
        >>> extract_symbols("Compare GOOGL and META earnings")
        ['GOOGL', 'META']
    """
    candidates = SYMBOL_PATTERN.findall(text)

    # Deduplicate while preserving order
    seen = set()
    unique_symbols = []
    for symbol in candidates:
        if symbol not in seen and symbol not in STOP_WORDS:
            seen.add(symbol)
            unique_symbols.append(symbol)

    return unique_symbols


def detect_action(text: str) -> str:
    """
    Detect the type of analysis/action from message text.

    Args:
        text: Message text to analyze

    Returns:
        Action string (e.g., "Technical Analysis", "Cash Flow", "Analysis")

    Examples:
        >>> detect_action("Show me the RSI for AAPL")
        'Technical Analysis'
        >>> detect_action("What's the cash flow for MRVL?")
        'Cash Flow'
    """
    text_lower = text.lower()

    if any(
        keyword in text_lower
        for keyword in (
            "deep analysis",
            "deep dive",
            "comprehensive analysis",
            "深度分析",
            "完整分析",
            "投资分析",
            "反方质疑",
            "多角度",
        )
    ):
        return "Deep Research"

    if any(
        keyword in text_lower
        for keyword in (
            "stock price",
            "current price",
            "how much",
            "trading at",
            "股价",
            "现价",
            "价格",
            "多少钱",
        )
    ):
        return "Price"

    for action, keywords in ACTION_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return action

    return "Analysis"


def _topic_excerpt(user_message: str) -> str:
    """Create a compact title from the user's own wording."""
    text = re.sub(r"\[Context:.*", "", user_message, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(
        r"^(?:please\s+|could you\s+|can you\s+|tell me\s+|show me\s+|"
        r"请(?:帮我)?|帮我|麻烦(?:帮我)?)",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = text.strip(" \t\r\n#*_`-—:：,，。!?！？")
    if not text:
        return "New Chat"
    if len(text) > MAX_TITLE_LENGTH:
        return text[: MAX_TITLE_LENGTH - 3].rstrip() + "..."
    return text


def generate_chat_title(
    user_message: str,
    assistant_response: str | None = None,
    current_symbol: str | None = None,
) -> str:
    """
    Generate a meaningful chat title from conversation content.

    Priority:
    1. Symbol + Action: "AAPL Technical Analysis"
    2. Multiple symbols: "AAPL vs MSFT" or "AAPL, MSFT Analysis"
    3. Symbol only: "MRVL Analysis"
    4. Topic only: "Portfolio Review"
    5. Fallback: "Chat Analysis"

    Args:
        user_message: User's first message
        assistant_response: Assistant's first response (optional, for additional context)

    Returns:
        Generated title (max 50 characters)

    Examples:
        >>> generate_chat_title("Analyze AAPL stock")
        'AAPL Analysis'
        >>> generate_chat_title("What's the cash flow for MRVL?")
        'MRVL Cash Flow'
        >>> generate_chat_title("Compare GOOGL and META")
        'GOOGL vs META'
    """
    # Explicit symbols take priority, then selected UI context, then symbols
    # grounded in the assistant's first response.
    symbols = extract_symbols(user_message)
    if not symbols and current_symbol:
        normalized_symbol = current_symbol.strip().upper()
        if normalized_symbol:
            symbols = [normalized_symbol]
    if not symbols and assistant_response:
        symbols = extract_symbols(assistant_response)

    # Detect action from user message
    action = detect_action(user_message)

    # Build title based on what we found
    if len(symbols) >= 2:
        # Multiple symbols - check for comparison
        if any(
            kw in user_message.lower()
            for kw in ["compare", "vs", "versus", "difference", "better"]
        ):
            title = f"{symbols[0]} vs {symbols[1]}"
        else:
            # List first 2-3 symbols
            symbol_str = ", ".join(symbols[:3])
            title = f"{symbol_str} {action}"
    elif len(symbols) == 1:
        # Single symbol
        title = f"{symbols[0]} {action}"
    else:
        # Preserve the user's topic instead of collapsing unrelated chats into
        # generic labels such as "Chat Analysis" or "Fundamental Analysis".
        title = _topic_excerpt(user_message)

    # Truncate if needed
    if len(title) > MAX_TITLE_LENGTH:
        title = title[: MAX_TITLE_LENGTH - 3] + "..."

    return title


def extract_title_from_response(response: Any) -> tuple[str | None, str | None]:
    """
    Extract LLM-generated title from response and return cleaned content.

    The LLM is instructed to include a title at the end of responses in format:
    [chat_title: Your Title Here]

    Args:
        response: Full LLM response text

    Returns:
        Tuple of (extracted_title, cleaned_response):
        - extracted_title: The title if found, None if not
        - cleaned_response: Response with title line removed

    Examples:
        >>> extract_title_from_response("Analysis here...\\n[chat_title: AAPL Analysis]")
        ('AAPL Analysis', 'Analysis here...')
        >>> extract_title_from_response("No title here")
        (None, 'No title here')
    """
    if response is None:
        return None, None

    response_text = message_content_to_text(response)
    if not response_text:
        return None, response_text

    # Search for title pattern at end of response
    match = CHAT_TITLE_PATTERN.search(response_text)

    if match:
        title = match.group(1).strip()

        # Validate title length (max 30 chars as per prompt instructions)
        if len(title) > 30:
            title = title[:27] + "..."

        # Remove the title line from response
        cleaned = response_text[: match.start()].rstrip()

        logger.info(
            "Extracted LLM-generated title",
            title=title,
            original_length=len(response_text),
            cleaned_length=len(cleaned),
        )

        return title, cleaned

    logger.debug("No LLM-generated title found in response")
    return None, response_text
