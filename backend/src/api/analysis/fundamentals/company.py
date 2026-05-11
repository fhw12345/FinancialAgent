"""
Company overview and fundamentals endpoints.

Provides company profile, overview, and comprehensive fundamental analysis
including valuation metrics, profitability, and growth indicators.
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
    CompanyOverviewResponse,
    StockFundamentalsRequest,
    StockFundamentalsResponse,
)
from ..shared import get_formatter, get_market_service

logger = structlog.get_logger()
router = APIRouter()


@router.post("/fundamentals", response_model=StockFundamentalsResponse)
async def stock_fundamentals(
    request: StockFundamentalsRequest,
    redis_cache: RedisCache = Depends(get_redis),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> StockFundamentalsResponse:
    """
    Get comprehensive fundamental analysis for a stock symbol.

    Uses Alpha Vantage COMPANY_OVERVIEW for fundamentals data.
    Includes valuation metrics, financial health indicators, and market data.
    """
    try:
        # Check cache first
        # Include date to prevent serving stale price data from previous day
        from datetime import UTC, datetime

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        cache_key = f"fundamentals:{request.symbol}:{current_date}"
        cached_result = await redis_cache.get(cache_key)
        if cached_result:
            return StockFundamentalsResponse.model_validate(cached_result)

        logger.info("Fetching fundamentals from Alpha Vantage", symbol=request.symbol)

        # Get company overview from Alpha Vantage
        overview = await market_service.get_company_overview(request.symbol)

        if not overview or "Symbol" not in overview:
            raise ValueError(
                f"'{request.symbol}' is not a valid stock symbol or no data available. "
                "Please check the symbol and try again."
            )

        # Extract fundamental metrics from Alpha Vantage OVERVIEW
        symbol = overview.get("Symbol", request.symbol)
        company_name = overview.get("Name", symbol)

        # Price Data
        current_price = safe_float(
            overview.get("50DayMovingAverage")
        )  # Use MA as proxy
        fifty_two_week_high = safe_float(overview.get("52WeekHigh"), current_price)
        fifty_two_week_low = safe_float(overview.get("52WeekLow"), current_price)

        # Market Metrics
        market_cap = safe_float(overview.get("MarketCapitalization"))

        # Valuation Ratios
        pe_ratio = (
            safe_float(overview.get("PERatio"))
            if overview.get("PERatio") != "None"
            else None
        )
        forward_pe = (
            safe_float(overview.get("ForwardPE"))
            if overview.get("ForwardPE") != "None"
            else None
        )
        pb_ratio = (
            safe_float(overview.get("PriceToBookRatio"))
            if overview.get("PriceToBookRatio") != "None"
            else None
        )
        peg_ratio = (
            safe_float(overview.get("PEGRatio"))
            if overview.get("PEGRatio") != "None"
            else None
        )
        price_to_sales = (
            safe_float(overview.get("PriceToSalesRatioTTM"))
            if overview.get("PriceToSalesRatioTTM") != "None"
            else None
        )

        # Profitability Metrics
        eps = safe_float(overview.get("EPS")) if overview.get("EPS") != "None" else None
        profit_margin_decimal = safe_float(overview.get("ProfitMargin"))
        profit_margin = (
            profit_margin_decimal * 100 if profit_margin_decimal > 0 else None
        )
        operating_margin_decimal = safe_float(overview.get("OperatingMarginTTM"))
        operating_margin = (
            operating_margin_decimal * 100 if operating_margin_decimal > 0 else None
        )

        # Return Metrics
        roe_decimal = safe_float(overview.get("ReturnOnEquityTTM"))
        roe = roe_decimal * 100 if roe_decimal > 0 else None
        roa_decimal = safe_float(overview.get("ReturnOnAssetsTTM"))
        roa = roa_decimal * 100 if roa_decimal > 0 else None

        # Growth Metrics
        revenue_ttm = safe_float(overview.get("RevenueTTM"))
        quarterly_earnings_growth_decimal = safe_float(
            overview.get("QuarterlyEarningsGrowthYOY")
        )
        quarterly_earnings_growth = (
            quarterly_earnings_growth_decimal * 100
            if quarterly_earnings_growth_decimal != 0
            else None
        )
        quarterly_revenue_growth_decimal = safe_float(
            overview.get("QuarterlyRevenueGrowthYOY")
        )
        quarterly_revenue_growth = (
            quarterly_revenue_growth_decimal * 100
            if quarterly_revenue_growth_decimal != 0
            else None
        )

        # Dividend & Risk
        dividend_yield_decimal = safe_float(overview.get("DividendYield"))
        dividend_yield = (
            dividend_yield_decimal * 100 if dividend_yield_decimal > 0 else None
        )
        beta = (
            safe_float(overview.get("Beta")) if overview.get("Beta") != "None" else None
        )

        # Analyst Data
        analyst_target_price = (
            safe_float(overview.get("AnalystTargetPrice"))
            if overview.get("AnalystTargetPrice") != "None"
            else None
        )

        # Calculate price position in 52-week range
        price_range = fifty_two_week_high - fifty_two_week_low
        position_in_range = (
            ((current_price - fifty_two_week_low) / price_range * 100)
            if price_range > 0
            else 50
        )

        # Market cap classification
        if market_cap > 200_000_000_000:
            cap_class = "mega-cap"
        elif market_cap > 10_000_000_000:
            cap_class = "large-cap"
        elif market_cap > 2_000_000_000:
            cap_class = "mid-cap"
        elif market_cap > 300_000_000:
            cap_class = "small-cap"
        else:
            cap_class = "micro-cap"

        # Generate summary
        summary = (
            f"{symbol} is a {cap_class} stock trading at ${current_price:.2f}, "
            f"which is {position_in_range:.1f}% of its 52-week range. "
        )

        if market_cap > 0:
            summary += f"Market cap: ${market_cap / 1e9:.1f}B. "

        key_metrics = [
            f"52-Week Range: ${fifty_two_week_low:.2f} - ${fifty_two_week_high:.2f}",
            f"Position in Range: {position_in_range:.1f}%",
            f"Market Cap Class: {cap_class.title()}",
        ]

        # Valuation Ratios Section
        if pe_ratio is not None and pe_ratio > 0:
            pe_interpretation = (
                "expensive"
                if pe_ratio > 25
                else "reasonable" if pe_ratio > 15 else "cheap"
            )
            key_metrics.append(f"P/E Ratio (TTM): {pe_ratio:.2f} ({pe_interpretation})")
            summary += (
                f"P/E ratio of {pe_ratio:.2f} suggests {pe_interpretation} valuation. "
            )

        if forward_pe is not None and forward_pe > 0:
            key_metrics.append(f"Forward P/E: {forward_pe:.2f}")

        if pb_ratio is not None and pb_ratio > 0:
            pb_interpretation = (
                "premium" if pb_ratio > 3 else "fair" if pb_ratio > 1 else "discount"
            )
            key_metrics.append(f"P/B Ratio: {pb_ratio:.2f} ({pb_interpretation})")

        if peg_ratio is not None and peg_ratio > 0:
            peg_interpretation = (
                "attractive"
                if peg_ratio < 1
                else "fair" if peg_ratio < 2 else "expensive"
            )
            key_metrics.append(f"PEG Ratio: {peg_ratio:.2f} ({peg_interpretation})")

        if price_to_sales is not None and price_to_sales > 0:
            key_metrics.append(f"Price/Sales (TTM): {price_to_sales:.2f}")

        # Profitability Section
        if eps is not None:
            key_metrics.append(f"EPS (TTM): ${eps:.2f}")

        if profit_margin is not None:
            margin_quality = (
                "excellent"
                if profit_margin > 20
                else "good" if profit_margin > 10 else "moderate"
            )
            key_metrics.append(
                f"Profit Margin: {profit_margin:.1f}% ({margin_quality})"
            )

        if operating_margin is not None:
            key_metrics.append(f"Operating Margin: {operating_margin:.1f}%")

        # Return Metrics Section
        if roe is not None:
            roe_quality = "strong" if roe > 15 else "average" if roe > 10 else "weak"
            key_metrics.append(f"Return on Equity: {roe:.1f}% ({roe_quality})")

        if roa is not None:
            key_metrics.append(f"Return on Assets: {roa:.1f}%")

        # Growth Metrics Section
        if revenue_ttm > 0:
            key_metrics.append(f"Revenue (TTM): ${revenue_ttm / 1e9:.2f}B")

        if quarterly_earnings_growth is not None:
            growth_trend = "growing" if quarterly_earnings_growth > 0 else "declining"
            key_metrics.append(
                f"Q Earnings Growth YoY: {quarterly_earnings_growth:+.1f}% ({growth_trend})"
            )

        if quarterly_revenue_growth is not None:
            growth_trend = "growing" if quarterly_revenue_growth > 0 else "declining"
            key_metrics.append(
                f"Q Revenue Growth YoY: {quarterly_revenue_growth:+.1f}% ({growth_trend})"
            )

        # Dividend & Risk Section
        if dividend_yield is not None and dividend_yield > 0:
            div_quality = (
                "high income"
                if dividend_yield > 4
                else "moderate income" if dividend_yield > 2 else "low income"
            )
            key_metrics.append(f"Dividend Yield: {dividend_yield:.2f}% ({div_quality})")
            if dividend_yield > 4:
                summary += "High dividend yield suggests income focus. "

        if beta is not None:
            volatility = "high" if beta > 1.5 else "moderate" if beta > 0.5 else "low"
            key_metrics.append(f"Beta: {beta:.2f} ({volatility} volatility)")

        # Analyst Target
        if analyst_target_price is not None and analyst_target_price > 0:
            upside_pct = (analyst_target_price - current_price) / current_price * 100
            upside_dir = "upside" if upside_pct > 0 else "downside"
            key_metrics.append(
                f"Analyst Target: ${analyst_target_price:.2f} ({upside_pct:+.1f}% {upside_dir})"
            )

        result = StockFundamentalsResponse(
            symbol=symbol,
            company_name=company_name,
            analysis_date=datetime.now(UTC).isoformat(),
            current_price=current_price,
            price_change=0.0,  # Not available from Alpha Vantage OVERVIEW
            price_change_percent=0.0,
            volume=0,  # Not available from Alpha Vantage OVERVIEW
            avg_volume=0,
            market_cap=market_cap,
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            dividend_yield=dividend_yield,
            beta=beta,
            fifty_two_week_high=fifty_two_week_high,
            fifty_two_week_low=fifty_two_week_low,
            fundamental_summary=summary,
            key_metrics=key_metrics,
        )

        # Cache for 24 hours - Fundamentals change quarterly (earnings)
        # Date-based cache key ensures fresh daily data
        settings = get_settings()
        await redis_cache.set(
            cache_key, result.model_dump(), ttl_seconds=settings.cache_ttl_fundamentals
        )

        logger.info("Fundamentals analysis completed", symbol=symbol)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid symbol: {str(e)}") from e
    except Exception as e:
        logger.error(
            "Fundamentals analysis failed", symbol=request.symbol, error=str(e)
        )
        raise HTTPException(
            status_code=500, detail=f"Fundamentals analysis failed: {str(e)}"
        ) from e


@router.post("/company-overview", response_model=CompanyOverviewResponse)
async def company_overview(
    request: StockFundamentalsRequest,
    redis_cache: RedisCache = Depends(get_redis),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
    formatter: AlphaVantageResponseFormatter = Depends(get_formatter),
) -> CompanyOverviewResponse:
    """
    Get comprehensive company overview with key metrics and ownership data.

    Uses Alpha Vantage COMPANY_OVERVIEW for company information.
    Returns formatted overview with description, metrics, ownership percentages.
    """
    try:
        # Check cache first
        from datetime import UTC, datetime

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        cache_key = f"company_overview:{request.symbol}:{current_date}"
        cached_result = await redis_cache.get(cache_key)
        if cached_result:
            # Cache may hold either a CompanyOverviewResponse dump (snake_case)
            # or the raw service overview dict (PascalCase, written by the
            # cache_warming_service). Only the former is directly model_validatable;
            # for the latter, fall through to the normal handler so it gets
            # transformed and re-cached in the right shape.
            if isinstance(cached_result, dict) and "symbol" in cached_result:
                return CompanyOverviewResponse.model_validate(cached_result)

        logger.info(
            "Fetching company overview from Alpha Vantage", symbol=request.symbol
        )

        # Get company overview from Alpha Vantage
        overview = await market_service.get_company_overview(request.symbol)

        if not overview or "Symbol" not in overview:
            raise ValueError(
                f"'{request.symbol}' is not a valid stock symbol or no data available. "
                "Please check the symbol and try again."
            )

        # Extract company info
        symbol = overview.get("Symbol", request.symbol)
        company_name = overview.get("Name", symbol)
        description = overview.get("Description", "N/A")
        industry = overview.get("Industry", "N/A")
        sector = overview.get("Sector", "N/A")
        exchange = overview.get("Exchange", "N/A")
        country = overview.get("Country", "N/A")

        # Extract key metrics
        market_cap = safe_float(overview.get("MarketCapitalization"))
        pe_ratio = safe_float(overview.get("PERatio"))
        eps = safe_float(overview.get("EPS"))
        profit_margin_decimal = safe_float(overview.get("ProfitMargin"))
        profit_margin = profit_margin_decimal * 100 if profit_margin_decimal else None
        revenue_ttm = safe_float(overview.get("RevenueTTM"))
        dividend_yield_decimal = safe_float(overview.get("DividendYield"))
        dividend_yield = (
            dividend_yield_decimal * 100 if dividend_yield_decimal else None
        )
        beta = safe_float(overview.get("Beta"))

        # Ownership metrics (Alpha Vantage returns as percentages already)
        percent_insiders = safe_float(overview.get("PercentInsiders"))
        percent_institutions = safe_float(overview.get("PercentInstitutions"))

        # Price metrics
        week_52_high = safe_float(overview.get("52WeekHigh"))
        week_52_low = safe_float(overview.get("52WeekLow"))

        # Build overview summary
        summary = f"{company_name} ({symbol}) operates in the {industry} industry within the {sector} sector. "
        summary += f"Listed on {exchange}. "

        # Build key metrics list
        key_metrics = []

        if market_cap:
            key_metrics.append(f"Market Cap: ${market_cap / 1e9:.2f}B")
        if pe_ratio:
            key_metrics.append(f"P/E Ratio: {pe_ratio:.2f}")
        if eps:
            key_metrics.append(f"EPS: ${eps:.2f}")
        if profit_margin:
            key_metrics.append(f"Profit Margin: {profit_margin:.2f}%")
        if revenue_ttm:
            key_metrics.append(f"Revenue (TTM): ${revenue_ttm / 1e9:.2f}B")
        if dividend_yield:
            key_metrics.append(f"Dividend Yield: {dividend_yield:.2f}%")
        if beta:
            key_metrics.append(f"Beta: {beta:.2f}")
        if percent_insiders:
            key_metrics.append(f"% Insiders: {percent_insiders:.2f}%")
        if percent_institutions:
            key_metrics.append(f"% Institutions: {percent_institutions:.2f}%")
        if week_52_high:
            key_metrics.append(f"52W High: ${week_52_high:.2f}")
        if week_52_low:
            key_metrics.append(f"52W Low: ${week_52_low:.2f}")

        # Generate rich markdown using formatter
        formatted_markdown = formatter.format_company_overview(
            raw_data=overview,
            symbol=symbol,
            invoked_at=datetime.now(UTC).isoformat(),
        )

        result = CompanyOverviewResponse(
            symbol=symbol,
            company_name=company_name,
            description=description,
            industry=industry,
            sector=sector,
            exchange=exchange,
            country=country,
            market_cap=market_cap,
            pe_ratio=pe_ratio,
            eps=eps,
            profit_margin=profit_margin,
            revenue_ttm=revenue_ttm,
            dividend_yield=dividend_yield,
            beta=beta,
            percent_insiders=percent_insiders,
            percent_institutions=percent_institutions,
            week_52_high=week_52_high,
            week_52_low=week_52_low,
            overview_summary=summary,
            key_metrics=key_metrics,
            formatted_markdown=formatted_markdown,
        )

        # Cache for 24 hours - Company info rarely changes
        settings = get_settings()
        await redis_cache.set(
            cache_key, result.model_dump(), ttl_seconds=settings.cache_ttl_fundamentals
        )

        logger.info(
            "Company overview completed", symbol=symbol, company_name=company_name
        )
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid symbol: {str(e)}") from e
    except Exception as e:
        logger.error("Company overview failed", symbol=request.symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Company overview failed: {str(e)}"
        ) from e
