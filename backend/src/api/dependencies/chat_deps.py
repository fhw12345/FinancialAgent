"""
Dependencies for chat API endpoints.
"""

from typing import Any

from fastapi import Depends

from ...agent.chat_agent import ChatAgent
from ...agent.langgraph_react_agent import FinancialAnalysisReActAgent
from ...core.config import Settings, get_settings
from ...core.data.ticker_data_service import TickerDataService
from ...database.mongodb import MongoDB
from ...database.redis import RedisCache
from ...database.repositories.chat_repository import ChatRepository
from ...database.repositories.message_repository import MessageRepository
from ...services.alphavantage_market_data import AlphaVantageMarketDataService
from ...services.chat_service import ChatService
from ...services.context_window_manager import ContextWindowManager
from .auth import get_current_user_id, get_mongodb  # Import shared auth

# ===== Agent Singleton (Per-Worker Process) =====
# Agent is expensive to initialize (300-500ms for LangGraph compilation)
# Cache it as module-level singleton to avoid re-compilation on every request

_react_agent_singleton: FinancialAnalysisReActAgent | None = None
_deep_agent_singleton = None  # DeepAgentAdapter | None — lazy import

# ===== MongoDB and Repository Dependencies =====


def get_redis() -> RedisCache:
    """Get RedisCache instance from app state."""
    from ...main import app

    redis_cache: RedisCache = app.state.redis
    return redis_cache


def get_chat_repository(mongodb: MongoDB = Depends(get_mongodb)) -> ChatRepository:
    """Get chat repository instance."""
    chats_collection = mongodb.get_collection("chats")
    return ChatRepository(chats_collection)


def get_message_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> MessageRepository:
    """Get message repository instance."""
    messages_collection = mongodb.get_collection("messages")
    return MessageRepository(messages_collection)


# ===== Service Dependencies =====


def get_chat_service(
    chat_repo: ChatRepository = Depends(get_chat_repository),
    message_repo: MessageRepository = Depends(get_message_repository),
    settings: Settings = Depends(get_settings),
) -> ChatService:
    """Get chat service instance."""
    return ChatService(chat_repo, message_repo, settings)


def get_context_manager(
    settings: Settings = Depends(get_settings),
) -> ContextWindowManager:
    """Get context window manager for automatic context compaction."""
    return ContextWindowManager(settings)


def get_chat_agent(
    settings: Settings = Depends(get_settings),
) -> ChatAgent:
    """
    Get or create chat agent instance.

    Lightweight LLM wrapper, no session management needed.
    """
    return ChatAgent(settings=settings)


def get_market_service() -> AlphaVantageMarketDataService:
    """Get AlphaVantage market service instance from app state."""
    from ...main import app
    from ...services.alphavantage_market_data import AlphaVantageMarketDataService

    market_service: AlphaVantageMarketDataService = app.state.market_service
    return market_service


def get_ticker_data_service(
    redis_cache: RedisCache = Depends(get_redis),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> TickerDataService:
    """Get ticker data service instance with AlphaVantage."""
    return TickerDataService(
        redis_cache=redis_cache, alpha_vantage_service=market_service
    )


def get_react_agent(
    settings: Settings = Depends(get_settings),
    ticker_service: TickerDataService = Depends(get_ticker_data_service),
    redis_cache: RedisCache = Depends(get_redis),
) -> FinancialAnalysisReActAgent:
    """
    Get SDK ReAct agent with MCP tools (120 total: 2 local + 118 MCP).

    This agent uses LangGraph's create_react_agent SDK for:
    - Autonomous tool chaining (LLM decides sequence)
    - Compressed tool results (2-3 lines vs 20KB dicts)
    - Built-in message history via MemorySaver
    - MCP protocol for Alpha Vantage tools (118 tools)

    Key difference from get_financial_analysis_agent:
    - LLM-driven routing (vs hardcoded conditional_router)
    - Can chain multiple tools per invocation
    - Auto-loop handles ReAct pattern
    - Access to 118 Alpha Vantage tools via MCP

    Performance: Agent is initialized during startup with MCP tools loaded.
    Falls back to local tools only if MCP initialization fails.
    """
    global _react_agent_singleton
    from ...main import app

    # Try to get pre-initialized agent from app state (includes MCP tools)
    if hasattr(app.state, "react_agent"):
        return app.state.react_agent

    # Fallback: Create agent without MCP tools (local only)
    # NOTE: This fallback path should rarely execute since main.py initializes
    # the agent with tool tracking. If you see this log frequently, investigate
    # why app.state.react_agent is None.
    if _react_agent_singleton is None:
        import structlog

        logger = structlog.get_logger()
        logger.warning(
            "Creating fallback agent without tool execution tracking",
            reason="app.state.react_agent not found",
        )

        # Get market_service from app state for fallback agent
        market_service = app.state.market_service

        _react_agent_singleton = FinancialAnalysisReActAgent(
            settings=settings,
            ticker_data_service=ticker_service,
            market_service=market_service,  # Required for agent tools
            # NOTE: tool_cache_wrapper not passed - no execution tracking in fallback mode
            redis_cache=redis_cache,  # Enable insights caching even in fallback mode
        )

    return _react_agent_singleton


def get_deep_agent(
    settings: Settings = Depends(get_settings),
    react_agent: FinancialAnalysisReActAgent = Depends(get_react_agent),
) -> Any:  # Returns DeepAgentAdapter — lazy import to avoid startup crash
    """
    Get Deep ReAct agent wrapped in the adapter for ainvoke() compatibility.

    The deep agent uses hierarchical sub-agents (Technical, News, Financial,
    Debater) with optional adversarial debate loop.

    Reuses the same tools as the standard ReAct agent to avoid duplication.
    """
    global _deep_agent_singleton

    if _deep_agent_singleton is not None:
        return _deep_agent_singleton

    import structlog

    from ...agent.deep_agent_adapter import DeepAgentAdapter
    from ...agent.deep_react_agent import DeepReActAgent

    _logger = structlog.get_logger()

    # Reuse tools from the existing react agent
    tools = react_agent.tools if hasattr(react_agent, "tools") else []

    deep_agent = DeepReActAgent(
        settings=settings,
        tools=tools,
        enable_debate=True,
    )

    _deep_agent_singleton = DeepAgentAdapter(deep_agent)
    _logger.info(
        "DeepAgentAdapter initialized",
        tool_count=len(tools),
    )

    return _deep_agent_singleton


# Re-export get_current_user_id for backward compatibility
__all__ = [
    "get_current_user_id",
    "get_chat_service",
    "get_chat_agent",
    "get_react_agent",
    "get_deep_agent",
    "get_context_manager",
    "get_message_repository",
]
