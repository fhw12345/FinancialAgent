"""
Dependencies for portfolio API endpoints.
"""

from fastapi import Depends

from ...core.config import Settings, get_settings
from ...core.data.ticker_data_service import TickerDataService
from ...database.mongodb import MongoDB
from ...database.redis import RedisCache
from ...database.repositories.holding_repository import HoldingRepository
from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ...services.alphavantage_market_data import AlphaVantageMarketDataService
from ...services.portfolio_service import PortfolioService
from .auth import get_mongodb  # Import shared auth
from .chat_deps import get_redis


def get_holding_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> HoldingRepository:
    """Get holding repository instance."""
    holdings_collection = mongodb.get_collection("holdings")
    return HoldingRepository(holdings_collection)


def get_portfolio_order_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> PortfolioOrderRepository:
    """Get portfolio order repository instance (suggested orders source)."""
    return PortfolioOrderRepository(mongodb.get_collection("portfolio_orders"))


def get_market_service() -> AlphaVantageMarketDataService:
    """Get AlphaVantage market service instance from app state."""
    from ...main import app

    market_service: AlphaVantageMarketDataService = app.state.market_service
    return market_service


def get_ticker_data_service(
    redis_cache: RedisCache = Depends(get_redis),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> TickerDataService:
    """Get ticker data service instance with AlphaVantage."""
    return TickerDataService(
        redis_cache=redis_cache,
        alpha_vantage_service=market_service,
    )


def get_portfolio_service(
    holding_repo: HoldingRepository = Depends(get_holding_repository),
    ticker_service: TickerDataService = Depends(get_ticker_data_service),
    settings: Settings = Depends(get_settings),
) -> PortfolioService:
    """Get portfolio service instance."""
    return PortfolioService(
        holding_repo=holding_repo,
        ticker_service=ticker_service,
        settings=settings,
    )
