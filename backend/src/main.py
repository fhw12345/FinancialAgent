"""
FastAPI application entry point for Financial Agent Backend.
Following Factor 11/12: Triggerable & Stateless design.

CI/CD: GitHub Actions automated deployment enabled.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .api.admin import router as admin_router
from .api.analysis import router as analysis_router
from .api.auth import router as auth_router
from .api.chat import router as chat_router
from .api.dependencies.rate_limit import limiter
from .api.dependencies.timing_middleware import TimingMiddleware
from .api.health import router as health_router
from .api.insights import router as insights_router
from .api.llm_models import router as llm_models_router
from .api.market_data import router as market_data_router
from .api.portfolio import router as portfolio_router
from .api.portfolio_admin import router as portfolio_admin_router
from .api.watchlist import router as watchlist_router
from .core.config import get_settings
from .core.exceptions import AppError
from .database.mongodb import MongoDB
from .database.redis import RedisCache

# Set the root logger level to INFO so we can see detailed logs
logging.basicConfig(level=logging.INFO)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan management for database connections."""
    settings = get_settings()

    logger.info("Starting Financial Agent Backend", environment=settings.environment)

    # Initialize database connections
    mongodb = MongoDB()
    redis_cache = RedisCache()

    # Initialize service variables before try block to ensure they're defined
    # in the finally block even if an early exception occurs
    market_service = None

    try:
        await mongodb.connect(settings.mongodb_url)
        await redis_cache.connect(settings.redis_url)

        # Create database indexes for optimal query performance
        from .database.repositories.chat_repository import ChatRepository
        from .database.repositories.message_repository import MessageRepository
        from .database.repositories.tool_execution_repository import (
            ToolExecutionRepository,
        )

        message_repo = MessageRepository(mongodb.get_collection("messages"))
        await message_repo.ensure_indexes()
        logger.info("Message indexes created")

        # Phase 2 indexes: Chat and Tool Execution
        chat_repo = ChatRepository(mongodb.get_collection("chats"))
        await chat_repo.ensure_indexes()
        logger.info("Chat indexes created (symbol-per-chat pattern)")

        tool_execution_repo = ToolExecutionRepository(
            mongodb.get_collection("tool_executions")
        )
        await tool_execution_repo.ensure_indexes()
        logger.info("Tool execution indexes created (audit trail + cost tracking)")

        # Portfolio indexes: Holdings
        from .database.repositories.holding_repository import HoldingRepository

        holding_repo = HoldingRepository(mongodb.get_collection("holdings"))
        await holding_repo.ensure_indexes()
        logger.info("Holding indexes created (portfolio management)")

        # Watchlist indexes
        from .database.repositories.watchlist_repository import WatchlistRepository

        watchlist_repo = WatchlistRepository(mongodb.get_collection("watchlist"))
        await watchlist_repo.ensure_indexes()
        logger.info("Watchlist indexes created (symbol tracking)")

        # Portfolio order indexes (order audit trail)
        from .database.repositories.portfolio_order_repository import (
            PortfolioOrderRepository,
        )

        order_repo = PortfolioOrderRepository(
            mongodb.get_collection("portfolio_orders")
        )
        await order_repo.ensure_indexes()
        logger.info("Portfolio order indexes created (order audit trail)")

        # User-entered transactions (manual buy/sell ledger)
        from .database.repositories.user_transaction_repository import (
            UserTransactionRepository,
        )

        user_tx_repo = UserTransactionRepository(
            mongodb.get_collection("user_transactions")
        )
        await user_tx_repo.ensure_indexes()
        logger.info("User transaction indexes created")

        # Initialize MCP tools for ReAct agent (if configured)
        # This loads 118 Alpha Vantage tools via MCP protocol
        from .agent.langgraph_react_agent import FinancialAnalysisReActAgent
        from .core.data.ticker_data_service import TickerDataService
        from .database.repositories.tool_execution_repository import (
            ToolExecutionRepository,
        )
        from .services.alphavantage_market_data import AlphaVantageMarketDataService
        from .services.data_manager import DataManager
        from .services.insights.snapshot_service import InsightsSnapshotService
        from .services.tool_cache_wrapper import ToolCacheWrapper

        react_agent = None
        try:
            # Create agent instance (will be cached as singleton in dependency injection)
            market_service = AlphaVantageMarketDataService(settings=settings)
            ticker_service = TickerDataService(
                redis_cache=redis_cache,
                alpha_vantage_service=market_service,
            )

            # Initialize tool execution tracking
            tool_exec_collection = mongodb.get_collection("tool_executions")
            tool_exec_repo = ToolExecutionRepository(tool_exec_collection)
            await tool_exec_repo.ensure_indexes()

            # Initialize tool cache wrapper for execution tracking
            tool_cache_wrapper = ToolCacheWrapper(
                redis_cache=redis_cache,
                tool_execution_repo=tool_exec_repo,
            )

            logger.info("Tool execution tracking initialized")

            # Story 2.5: Initialize DataManager and InsightsSnapshotService
            # for cache-first reads in AI tools (< 100ms response time)
            finnhub_service = None
            if settings.finnhub_api_key:
                from src.services.finnhub import FinnhubService

                finnhub_service = FinnhubService(api_key=settings.finnhub_api_key)
                logger.info(
                    "Finnhub service initialized (primary for quote/news/insider)"
                )

            data_manager = DataManager(
                redis_cache=redis_cache,
                alpha_vantage_service=market_service,
                finnhub_service=finnhub_service,
            )
            snapshot_service = InsightsSnapshotService(
                mongodb=mongodb,
                redis_cache=redis_cache,
                data_manager=data_manager,
                settings=settings,
            )
            logger.info(
                "InsightsSnapshotService initialized for cache-first tool reads"
            )

            # Store DataManager and SnapshotService in app state for admin API access
            app.state.data_manager = data_manager
            app.state.snapshot_service = snapshot_service
            # Make MongoDB reachable from background tasks too (used by
            # portfolio_admin two-button flows).
            app.state.mongodb = mongodb

            # Create agent with tool cache wrapper and Redis for insights caching
            react_agent = FinancialAnalysisReActAgent(
                settings=settings,
                ticker_data_service=ticker_service,
                market_service=market_service,
                tool_cache_wrapper=tool_cache_wrapper,
                redis_cache=redis_cache,  # Enable 30min caching for AI Sector Risk
                snapshot_service=snapshot_service,  # Story 2.5: Cache-first insights
                data_manager=data_manager,  # Singleton DataManager for cached OHLCV
            )

            # Store in app state for use in dependencies
            app.state.react_agent = react_agent
            app.state.market_service = market_service
            app.state.settings = settings
            logger.info("ReAct agent initialized")

            # Build PortfolioAnalysisAgent singleton — used by the dashboard
            # two-button flows (Analyze My Holdings + Today's Picks) so we
            # don't re-initialize the LangGraph graph on every click.
            try:
                from .agent.portfolio.agent import PortfolioAnalysisAgent

                app.state.portfolio_agent = PortfolioAnalysisAgent(
                    settings=settings,
                    mongodb=mongodb,
                    react_agent=react_agent,
                    market_service=market_service,
                    trading_service=None,  # Alpaca removed in W5a
                )
                logger.info("PortfolioAnalysisAgent initialized for dashboard flows")
            except Exception as _pa_e:
                logger.warning(
                    "PortfolioAnalysisAgent init failed — two-button flows will fall back to simplified path",
                    error=str(_pa_e),
                )
                app.state.portfolio_agent = None

        except Exception as e:
            logger.warning(
                "Failed to initialize ReAct agent - will continue without agent",
                error=str(e),
                error_type=type(e).__name__,
            )

        # Initialize watchlist analyzer (manual trigger only, no auto-run)
        from .services.watchlist_analyzer import WatchlistAnalyzer

        watchlist_analyzer = WatchlistAnalyzer(
            watchlist_collection=mongodb.get_collection("watchlist"),
            messages_collection=mongodb.get_collection("messages"),
            chats_collection=mongodb.get_collection("chats"),
            redis_cache=redis_cache,
            market_service=market_service,  # Pass Alpha Vantage service for price data
            settings=settings,  # Pass application settings for context management
            agent=react_agent,  # Pass agent for LLM-based analysis
            trading_service=None,  # Alpaca trading removed; orders are suggestions only
            order_repository=order_repo,  # Pass order repository for MongoDB persistence
            data_manager=data_manager,  # Singleton DataManager for cached OHLCV access
        )

        # Store in app state for manual triggering via API
        app.state.watchlist_analyzer = watchlist_analyzer
        logger.info(
            "Watchlist analyzer initialized (manual trigger mode)"
            + (" with agent" if react_agent else " without agent")
        )

        # Store in app state for dependency injection
        app.state.mongodb = mongodb
        app.state.redis = redis_cache
        app.state.market_service = market_service

        # Initialize Market Insights registry (singleton for all requests)
        from .services.insights import InsightsCategoryRegistry
        from .services.market_data import FREDService

        # Create FRED service for liquidity metrics
        fred_service = None
        if settings.fred_api_key:
            fred_service = FREDService(api_key=settings.fred_api_key)
            logger.info("FRED service initialized for liquidity metrics")

        insights_registry = InsightsCategoryRegistry(
            settings=settings,
            redis_cache=redis_cache,
            market_service=market_service,
            fred_service=fred_service,
        )
        app.state.insights_registry = insights_registry
        logger.info(
            "Insights registry initialized",
            category_count=len(insights_registry.list_categories()),
        )

        # Initialize cache warming service and run startup warming in background
        from .services.cache_warming_service import CacheWarmingService

        cache_warming_service = CacheWarmingService(
            redis_cache=redis_cache,
            market_service=market_service,
            watchlist_collection=mongodb.get_collection("watchlist"),
            settings=settings,
        )
        app.state.cache_warming_service = cache_warming_service

        # Run cache warming in background task (non-blocking)
        async def warm_cache_background() -> None:
            """Background task to warm cache on startup."""
            try:
                # Small delay to let other startup tasks complete first
                await asyncio.sleep(2)
                await cache_warming_service.warm_startup_cache()
            except Exception as e:
                logger.warning("Background cache warming failed", error=str(e))

        asyncio.create_task(warm_cache_background())
        logger.info("Cache warming service initialized (background warming started)")

        logger.info("Database connections started")

        yield

    finally:
        # Cleanup database connections
        await mongodb.disconnect()
        await redis_cache.disconnect()
        logger.info("Database connections stopped")

        # Cleanup Alpha Vantage HTTP client
        if market_service:
            await market_service.close()
            logger.info("Alpha Vantage service closed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Financial Agent API",
        description="AI-Enhanced Financial Analysis Platform",
        version="0.1.0",
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url="/redoc" if settings.environment == "development" else None,
        lifespan=lifespan,
    )

    # Security middleware - only in production
    if settings.environment == "production":
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts,
        )

    # CORS middleware for frontend communication
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    # Request timing middleware for performance profiling
    # Added first so it wraps all other middleware and measures total time
    if settings.environment != "test":
        app.add_middleware(
            TimingMiddleware,
            log_all_requests=False,  # Only log slow requests by default
            slow_threshold_ms=500.0,  # Log requests slower than 500ms
        )

    # Rate limiting - SlowAPI integration
    app.state.limiter = limiter
    # Only add middleware in non-test environments (middleware breaks FastAPI TestClient)
    if settings.environment != "test":
        app.add_middleware(SlowAPIMiddleware)  # This middleware enforces rate limits

    # Custom rate limit exception handler that handles both RateLimitExceeded and connection errors
    @app.exception_handler(RateLimitExceeded)
    async def custom_rate_limit_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle rate limit exceeded errors gracefully, including Redis connection failures."""
        # Check if this is a RateLimitExceeded exception
        if isinstance(exc, RateLimitExceeded):
            return JSONResponse(
                status_code=429,
                content={"error": f"Rate limit exceeded: {exc.detail}"},
                headers={"Retry-After": str(60)},
            )
        # Handle other exceptions (like ConnectionError from Redis)
        else:
            logger.warning(
                "Rate limiting error occurred",
                error=str(exc),
                error_type=type(exc).__name__,
                path=request.url.path,
            )
            # Allow request to proceed if Redis is unavailable (graceful degradation)
            return JSONResponse(
                status_code=503,
                content={"error": "Rate limiting temporarily unavailable"},
            )

    # Global exception handler for custom app errors
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """
        Handle all custom AppError exceptions with proper HTTP status codes.

        This prevents DatabaseError, ConfigurationError, etc. from appearing as
        generic 500 errors, making debugging much faster.
        """
        error_dict = exc.to_dict()

        # Log error with full context
        logger.error(
            "Application error occurred",
            path=request.url.path,
            method=request.method,
            **error_dict,
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "error_type": exc.error_type},
        )

    # Include routers
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(admin_router)  # Admin-only monitoring endpoints
    app.include_router(auth_router)
    app.include_router(analysis_router)
    app.include_router(market_data_router)
    app.include_router(chat_router)  # Persistent MongoDB-based chat
    app.include_router(portfolio_router)  # Portfolio holdings management
    app.include_router(portfolio_admin_router)  # Two-button analysis + settings
    app.include_router(watchlist_router)  # Watchlist symbol tracking
    app.include_router(llm_models_router)  # LLM model selection and pricing
    app.include_router(insights_router)  # Market Insights Platform

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint for basic connectivity check."""
        return {
            "message": "Financial Agent API",
            "version": "0.1.0",
            "environment": settings.environment,
        }

    return app


# Create app instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # nosec B104 - Required for Docker container
        port=8000,
        reload=settings.environment == "development",
        log_config=None,  # Use structlog configuration
    )
