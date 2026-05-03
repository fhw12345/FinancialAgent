"""
Financial statements endpoints.

Provides access to cash flow statements, balance sheets, and earnings data
for fundamental financial analysis.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException

from ....core.config import get_settings
from ....database.redis import RedisCache
from ....services.alphavantage_market_data import AlphaVantageMarketDataService
from ....services.alphavantage_response_formatter import (
    AlphaVantageResponseFormatter,
)
from ....shared.formatters import safe_float
from ...health import get_redis
from ...models import (
    BalanceSheetResponse,
    CashFlowResponse,
    StockFundamentalsRequest,
)
from ..shared import get_formatter, get_market_service

logger = structlog.get_logger()
router = APIRouter()


@router.post("/cash-flow", response_model=CashFlowResponse)
async def cash_flow(
    request: StockFundamentalsRequest,
    redis_cache: RedisCache = Depends(get_redis),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
    formatter: AlphaVantageResponseFormatter = Depends(get_formatter),
) -> CashFlowResponse:
    """Get cash flow statement for a company."""
    try:
        from datetime import UTC, datetime

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        cache_key = f"cash_flow:{request.symbol}:{current_date}"
        cached_result = await redis_cache.get(cache_key)
        if cached_result:
            return CashFlowResponse.model_validate(cached_result)

        logger.info("Fetching cash flow from Alpha Vantage", symbol=request.symbol)

        data = await market_service.get_cash_flow(request.symbol)
        annual = data.get("annualReports", [])

        if not annual:
            raise ValueError(f"No cash flow data available for {request.symbol}")

        latest = annual[0]
        company_name = data.get("symbol", request.symbol)

        operating_cf = safe_float(latest.get("operatingCashflow"))
        capex = safe_float(latest.get("capitalExpenditures"))
        free_cf = (operating_cf - abs(capex)) if operating_cf and capex else None
        dividend = safe_float(latest.get("dividendPayout"))

        summary = f"Latest annual cash flow for {company_name} ({latest.get('fiscalDateEnding')}). "
        if operating_cf:
            summary += f"Operating cash flow: ${operating_cf / 1e6:.1f}M. "
        if free_cf:
            summary += f"Free cash flow: ${free_cf / 1e6:.1f}M. "

        # Generate rich markdown using formatter
        formatted_markdown = formatter.format_cash_flow(
            raw_data=data,
            symbol=request.symbol,
            invoked_at=datetime.now(UTC).isoformat(),
        )

        result = CashFlowResponse(
            symbol=request.symbol,
            company_name=company_name,
            fiscal_date_ending=latest.get("fiscalDateEnding", "N/A"),
            operating_cashflow=operating_cf,
            capital_expenditures=capex,
            free_cashflow=free_cf,
            dividend_payout=dividend,
            cashflow_summary=summary,
            formatted_markdown=formatted_markdown,
        )

        settings = get_settings()
        await redis_cache.set(
            cache_key, result.model_dump(), ttl_seconds=settings.cache_ttl_fundamentals
        )
        logger.info("Cash flow completed", symbol=request.symbol)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid symbol: {str(e)}") from e
    except Exception as e:
        logger.error("Cash flow failed", symbol=request.symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Cash flow failed: {str(e)}"
        ) from e


@router.post("/balance-sheet", response_model=BalanceSheetResponse)
async def balance_sheet(
    request: StockFundamentalsRequest,
    redis_cache: RedisCache = Depends(get_redis),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
    formatter: AlphaVantageResponseFormatter = Depends(get_formatter),
) -> BalanceSheetResponse:
    """Get balance sheet for a company."""
    try:
        from datetime import UTC, datetime

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        cache_key = f"balance_sheet:{request.symbol}:{current_date}"
        cached_result = await redis_cache.get(cache_key)
        if cached_result:
            return BalanceSheetResponse.model_validate(cached_result)

        logger.info("Fetching balance sheet from Alpha Vantage", symbol=request.symbol)

        data = await market_service.get_balance_sheet(request.symbol)
        annual = data.get("annualReports", [])

        if not annual:
            raise ValueError(f"No balance sheet data available for {request.symbol}")

        latest = annual[0]
        company_name = data.get("symbol", request.symbol)

        total_assets = safe_float(latest.get("totalAssets"))
        total_liabilities = safe_float(latest.get("totalLiabilities"))
        equity = safe_float(latest.get("totalShareholderEquity"))
        current_assets = safe_float(latest.get("currentAssets"))
        current_liabilities = safe_float(latest.get("currentLiabilities"))
        cash = safe_float(latest.get("cashAndCashEquivalentsAtCarryingValue"))

        summary = f"Latest annual balance sheet for {company_name} ({latest.get('fiscalDateEnding')}). "
        if total_assets:
            summary += f"Total assets: ${total_assets / 1e6:.1f}M. "
        if equity:
            summary += f"Shareholder equity: ${equity / 1e6:.1f}M. "

        # Generate rich markdown using formatter
        formatted_markdown = formatter.format_balance_sheet(
            raw_data=data,
            symbol=request.symbol,
            invoked_at=datetime.now(UTC).isoformat(),
        )

        result = BalanceSheetResponse(
            symbol=request.symbol,
            company_name=company_name,
            fiscal_date_ending=latest.get("fiscalDateEnding", "N/A"),
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            total_shareholder_equity=equity,
            current_assets=current_assets,
            current_liabilities=current_liabilities,
            cash_and_equivalents=cash,
            balance_sheet_summary=summary,
            formatted_markdown=formatted_markdown,
        )

        settings = get_settings()
        await redis_cache.set(
            cache_key, result.model_dump(), ttl_seconds=settings.cache_ttl_fundamentals
        )
        logger.info("Balance sheet completed", symbol=request.symbol)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid symbol: {str(e)}") from e
    except Exception as e:
        logger.error("Balance sheet failed", symbol=request.symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Balance sheet failed: {str(e)}"
        ) from e
