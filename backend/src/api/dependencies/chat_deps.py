"""
Dependencies for chat API endpoints.
"""

from typing import Any

from fastapi import Depends

from ...agent.chat_agent import ChatAgent
from ...agent.flow_router import AgentFlowRouter
from ...agent.langgraph_react_agent import FinancialAnalysisReActAgent
from ...agent.symbol_resolver import SymbolResolver
from ...core.config import Settings, get_settings
from ...database.mongodb import MongoDB
from ...database.redis import RedisCache
from ...database.repositories.chat_repository import ChatRepository
from ...database.repositories.message_repository import MessageRepository
from ...services.alphavantage_market_data import AlphaVantageMarketDataService
from ...services.chat_service import ChatService
from ...services.context_window_manager import ContextWindowManager
from ...services.symbol_search_service import SymbolSearchService
from .storage import get_mongodb

# ===== Agent Singleton (Per-Worker Process) =====
# Agent is expensive to initialize (300-500ms for LangGraph compilation)
# Cache it as module-level singleton to avoid re-compilation on every request

_react_agent_singleton: FinancialAnalysisReActAgent | None = None
_deep_agent_singleton = None  # DeepAgentAdapter | None — lazy import
_flow_router_singleton: AgentFlowRouter | None = None

# ===== MongoDB and Repository Dependencies =====


def get_redis() -> RedisCache:
    """Get RedisCache instance from app state."""
    from ...main import app

    redis_cache: RedisCache = app.state.redis
    return redis_cache


def get_chat_repository(
    mongodb: MongoDB = Depends(get_mongodb),
    redis_cache: RedisCache = Depends(get_redis),
) -> ChatRepository:
    """Get chat repository instance."""
    chats_collection = mongodb.get_collection("chats")
    return ChatRepository(chats_collection, redis_cache)


def get_message_repository(
    mongodb: MongoDB = Depends(get_mongodb),
    redis_cache: RedisCache = Depends(get_redis),
) -> MessageRepository:
    """Get message repository instance."""
    messages_collection = mongodb.get_collection("messages")
    return MessageRepository(messages_collection, redis_cache)


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


def get_flow_router() -> AgentFlowRouter:
    """Get the shared hybrid chat-flow router."""
    global _flow_router_singleton
    if _flow_router_singleton is None:
        _flow_router_singleton = AgentFlowRouter()
    return _flow_router_singleton


def get_market_service() -> AlphaVantageMarketDataService:
    """Get AlphaVantage market service instance from app state."""
    from ...main import app
    from ...services.alphavantage_market_data import AlphaVantageMarketDataService

    market_service: AlphaVantageMarketDataService = app.state.market_service
    return market_service


def get_react_agent(
    settings: Settings = Depends(get_settings),
    redis_cache: RedisCache = Depends(get_redis),
) -> FinancialAnalysisReActAgent:
    """
    Get the pre-initialized SDK ReAct agent with local tools.

    This agent uses LangGraph's create_react_agent SDK for:
    - Autonomous tool chaining (LLM decides sequence)
    - Compressed tool results (2-3 lines vs 20KB dicts)
    - Built-in message history via MemorySaver
    - Local market-data, analysis, insights, and options tools

    Key difference from get_financial_analysis_agent:
    - LLM-driven routing (vs hardcoded conditional_router)
    - Can chain multiple tools per invocation
    - Auto-loop handles ReAct pattern
    - Shared DataManager fallback and Redis caching

    The agent is initialized during startup and reused per worker process.
    """
    global _react_agent_singleton
    from ...main import app

    # Prefer the pre-initialized agent from app state.
    if hasattr(app.state, "react_agent"):
        return app.state.react_agent

    # Fallback: create the same local agent lazily.
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
            market_service=market_service,  # Required for agent tools
            # NOTE: tool_cache_wrapper not passed - no execution tracking in fallback mode
            redis_cache=redis_cache,  # Enable insights caching even in fallback mode
        )

    return _react_agent_singleton


def get_deep_agent(
    settings: Settings = Depends(get_settings),
    react_agent: FinancialAnalysisReActAgent = Depends(get_react_agent),
    mongodb: MongoDB = Depends(get_mongodb),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
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

    # Reuse tools + DataManager from the existing react agent. Inject
    # order_repo/data_manager so verdicts get persisted as decision rows
    # for the decision tracker.
    tools = react_agent.tools if hasattr(react_agent, "tools") else []
    data_manager = getattr(react_agent, "data_manager", None)
    order_repo = None
    try:
        from ...database.repositories.portfolio_order_repository import (
            PortfolioOrderRepository,
        )

        order_repo = PortfolioOrderRepository(
            mongodb.get_collection("portfolio_orders")
        )
    except Exception as _e:
        _logger.warning("deep_react_order_repo_unavailable", error=str(_e))

    deep_agent = DeepReActAgent(
        settings=settings,
        tools=tools,
        enable_debate=True,
        order_repo=order_repo,
        data_manager=data_manager,
    )

    symbol_resolver = SymbolResolver(
        SymbolSearchService(market_service),
        settings=settings,
    )
    _deep_agent_singleton = DeepAgentAdapter(deep_agent, symbol_resolver)
    _logger.info(
        "DeepAgentAdapter initialized",
        tool_count=len(tools),
    )

    return _deep_agent_singleton


__all__ = [
    "get_chat_service",
    "get_chat_agent",
    "get_flow_router",
    "get_react_agent",
    "get_deep_agent",
    "get_context_manager",
    "get_message_repository",
]
