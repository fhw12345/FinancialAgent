"""
Application configuration using Pydantic Settings.
Following Factor 1: Own Your Configuration.

Supports hierarchical environment configuration:
- .env.base: Common non-secret defaults (committed to git)
- .env.{ENVIRONMENT}: Environment-specific overrides (gitignored)
- Environment variables: Highest priority
"""

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Get environment from env var, default to development
ENV = os.getenv("ENVIRONMENT", "development")


class Settings(BaseSettings):
    """Application settings with hierarchical env file support."""

    model_config = SettingsConfigDict(
        # Load base first, then environment-specific override
        env_file=[
            ".env.base",  # Common defaults (committed)
            f".env.{ENV}",  # Environment overrides (gitignored)
        ],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "test"] = "development"

    # Database connections
    mongodb_url: str = "mongodb://localhost:27017/financial_agent"
    redis_url: str = "redis://localhost:6379"

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Langfuse observability configuration (optional, off by default)
    # When langfuse_enabled=False, the @observe decorator becomes a no-op
    # and the langfuse Python package is not required.
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None

    # LLM provider routing
    llm_provider: Literal["maestro", "anthropic", "copilot_reverse"] = "maestro"

    # Agent Maestro
    maestro_base_url: str = "http://localhost:23333/api/anthropic"
    maestro_auth_token: str = "Powered by Agent Maestro"

    # Direct Anthropic API
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_key: str = ""
    anthropic_model: str = ""

    # GitHub Copilot reverse proxy. The sibling repository is named
    # copilot-bridge; the public flag remains copilot_reverse.
    copilot_reverse_base_url: str = "http://localhost:8765/cc"
    copilot_reverse_auth_token: str = "dummy"
    copilot_reverse_model: str = ""

    # Agent Maestro role assignments
    model_deep_planner: str = "claude-opus-4.8"
    model_react_agent: str = "claude-sonnet-5"
    model_portfolio_decisions: str = "claude-opus-4.8"
    model_verdict: str = "claude-opus-4.8"
    model_sub_technical: str = "claude-sonnet-5"
    model_simple_chat: str = "claude-haiku-4.5"
    model_sub_financial: str = "gpt-5.6-sol"
    model_portfolio_research: str = "gpt-5.6-sol"
    model_sub_debater: str = "gemini-3.1-pro-preview"
    model_sub_news: str = "gemini-3.5-flash"
    model_summary: str = "gemini-3.5-flash"

    default_llm_temperature: float = 0.7

    # Context window management
    llm_context_limit: int = 200_000
    compact_threshold_ratio: float = 0.75
    compact_target_ratio: float = 0.25
    tail_messages_keep: int = 3

    # External APIs - Market Data
    # W7: All paid market-data keys removed. yfinance (free, no key) is the
    # default data source. Alpha Vantage key kept as optional for users who
    # already have one — when empty the service falls back to yfinance.
    alpha_vantage_api_key: str = ""  # optional, falls back to yfinance when empty
    fred_api_key: str = ""  # FRED API key (free, register at fred.stlouisfed.org)
    exa_api_key: str = (
        ""  # Exa search key for debater independent verification (free 1k/mo, dashboard.exa.ai)
    )
    finnhub_api_key: str = (
        ""  # Finnhub key (free 60/min, register at finnhub.io). Primary for quote/news/insider.
    )

    # Development mode settings
    dev_analysis_symbols: str = (
        ""  # Comma-separated symbols to analyze in dev mode (empty = all)
    )

    # Cache settings - TTL values in seconds by data category
    # These values are optimized based on data freshness requirements
    redis_ttl_seconds: int = 3600  # 1 hour default cache TTL
    cache_ttl_realtime: int = 60  # Real-time quotes (1 min)
    cache_ttl_price_data: int = 300  # Price data (5 min)
    cache_ttl_analysis: int = 1800  # Analysis results (30 min)
    cache_ttl_news: int = 3600  # News/sentiment (1 hour)
    cache_ttl_historical: int = 7200  # Historical data (2 hours)
    cache_ttl_fundamentals: int = 86400  # Company fundamentals (24 hours)
    cache_ttl_insights: int = 86400  # AI insights (24 hours)

    # Alpha Vantage Fundamentals Tool Limits
    fundamentals_max_quarterly_periods: int = (
        20  # Max quarterly periods for cash flow/balance sheet
    )
    fundamentals_max_annual_periods: int = (
        5  # Max annual periods for cash flow/balance sheet
    )

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # per minute

    # Token budget limits per request type (Story 1.4: Token Usage Optimization)
    # Limits help control costs and ensure predictable response times
    token_budget_chat: int = 8000  # Regular chat messages
    token_budget_analysis: int = 16000  # Analysis requests with tool calls
    token_budget_portfolio: int = 32000  # Portfolio analysis (multi-symbol)
    token_budget_summary: int = 4000  # Context summarization
    token_warning_threshold: float = 0.8  # Warn at 80% of budget

    # Portfolio Analysis settings
    portfolio_analysis_batch_size: int = 5  # Concurrent symbol analysis batch size
    portfolio_analysis_min_success_rate: float = (
        0.7  # Min Phase 1 success rate for Phase 2
    )

    @property
    def database_name(self) -> str:
        """Extract database name from MongoDB URL."""
        # Extract database name and strip query parameters
        db_with_params = self.mongodb_url.split("/")[-1]
        return db_with_params.split("?")[0] if "?" in db_with_params else db_with_params

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
