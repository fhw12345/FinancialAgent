"""AI Sector Risk category implementation.

This category measures AI sector bubble risk using 7 quantitative
indicators from Alpha Vantage and FRED data. The composite index provides
an overall risk assessment for AI-related investments.

Metrics:
1. AI Price Anomaly - Z-score of AI stocks vs 200 SMA
2. News Sentiment - Normalized sentiment from NEWS_SENTIMENT
3. Smart Money Flow - Smart Money Index (Last Hour - First Hour returns)
4. Options Put/Call Ratio - ATM Dollar-Weighted PCR (contrarian indicator)
5. IPO Heat - IPO count in 90-day window
6. Market Liquidity - FRED-based RRP balance, SOFR-EFFR spread (replaces yield_curve)
7. Fed Expectations - 2Y yield slope

Theory: "When capital is abundant, asset prices easily rise and bubbles can form.
When capital is tight, even with high market sentiment, bubbles cannot easily form."

Interpretation Zones:
- 0-25: Low risk / Accumulation zone (Green)
- 25-50: Normal bull market (Blue)
- 50-75: Elevated / Caution (Yellow)
- 75-100: High risk / Euphoria (Red)
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import structlog

from ...data_manager import DataManager
from ..base import InsightCategoryBase
from ..models import InsightMetric, MetricExplanation, MetricStatus, ThresholdConfig
from ..registry import register_category

logger = structlog.get_logger()

# ETF used for dynamic AI basket (Global X Artificial Intelligence & Technology ETF)
AI_ETF_SYMBOL = "AIQ"

# Fallback symbols if ETF fetch fails
AI_BASKET_FALLBACK = ["NVDA", "MSFT", "AMD", "PLTR", "GOOGL", "META"]

# Number of top holdings to use from ETF
AI_BASKET_TOP_N = 10

# Cache key for ETF-derived basket
AI_BASKET_CACHE_KEY = "insights:ai_basket_symbols"
AI_BASKET_CACHE_TTL = 86400  # 24 hours (ETF holdings change infrequently)

# Market Liquidity calculation constants (FRED-based)
RRP_PEAK_BILLIONS = 2500  # Dec 2022 peak RRP balance
SPREAD_STRESS_THRESHOLD_BPS = 50  # SOFR-EFFR spread indicating funding stress
RRP_TREND_CHANGE_RANGE_PCT = 50  # Range for 20-day RRP change normalization


@register_category
class AISectorRiskCategory(InsightCategoryBase):
    """AI Sector Risk assessment category.

    Measures bubble risk in the AI sector using 7 quantitative
    indicators with weighted composite scoring.
    """

    CATEGORY_ID = "ai_sector_risk"
    CATEGORY_NAME = "AI Sector Risk"
    CATEGORY_ICON = "🎯"
    CATEGORY_DESCRIPTION = (
        "Measures bubble risk in the AI sector using price anomalies, "
        "sentiment, smart money flow, IPO activity, and yield curve signals. "
        "Higher scores indicate elevated euphoria and potential correction risk."
    )

    # Cache for 24 hours.
    CACHE_TTL_SECONDS = 86400

    def get_metric_definitions(self) -> list[dict[str, Any]]:
        """Return metric definitions for AI Sector Risk."""
        return [
            {
                "id": "ai_price_anomaly",
                "name": "AI Price Anomaly",
                "weight": 0.17,
                "data_sources": ["TIME_SERIES_DAILY"],
                "description": "Z-score of AI stocks vs 200-day SMA",
            },
            {
                "id": "news_sentiment",
                "name": "News Sentiment",
                "weight": 0.17,
                "data_sources": ["NEWS_SENTIMENT"],
                "description": "Normalized AI news sentiment (-0.35 to +0.35 → 0-100)",
            },
            {
                "id": "smart_money_flow",
                "name": "Smart Money Flow",
                "weight": 0.17,
                "data_sources": ["TIME_SERIES_INTRADAY"],
                "description": "Smart Money Index: Last hour return minus first hour return",
            },
            {
                "id": "options_put_call_ratio",
                "name": "Options Put/Call Ratio",
                "weight": 0.15,
                "data_sources": ["HISTORICAL_OPTIONS", "GLOBAL_QUOTE"],
                "description": "ATM Dollar-Weighted Put/Call Ratio (contrarian indicator)",
            },
            {
                "id": "ipo_heat",
                "name": "IPO Heat",
                "weight": 0.09,
                "data_sources": ["IPO_CALENDAR"],
                "description": "Count of tech IPOs in next 90 days",
            },
            {
                "id": "market_liquidity",
                "name": "Market Liquidity",
                "weight": 0.13,
                "data_sources": ["FRED_SOFR", "FRED_EFFR", "FRED_RRP"],
                "description": "RRP balance + SOFR-EFFR spread (actual liquidity)",
            },
            {
                "id": "fed_expectations",
                "name": "Fed Expectations",
                "weight": 0.12,
                "data_sources": ["TREASURY_YIELD"],
                "description": "2Y yield slope over 20 days",
            },
        ]

    def get_composite_weights(self) -> dict[str, float]:
        """Return weights for composite score calculation.

        7 metrics totaling 100%:
        - ai_price_anomaly: 17%
        - news_sentiment: 17%
        - smart_money_flow: 17%
        - options_put_call_ratio: 15%
        - ipo_heat: 9%
        - market_liquidity: 13% (replaces yield_curve)
        - fed_expectations: 12%
        """
        return {
            "ai_price_anomaly": 0.17,
            "news_sentiment": 0.17,
            "smart_money_flow": 0.17,
            "options_put_call_ratio": 0.15,
            "ipo_heat": 0.09,
            "market_liquidity": 0.13,
            "fed_expectations": 0.12,
        }

    async def _get_ai_basket_symbols(self) -> tuple[list[str], str]:
        """Get AI basket symbols dynamically from AIQ ETF holdings.

        Fetches top holdings from the Global X AI & Technology ETF (AIQ)
        and filters for valid US-traded symbols. Results are cached for
        24 hours since ETF holdings change infrequently.

        Returns:
            Tuple of (symbols list, source description)
        """
        # Check cache first
        if self.redis_cache:
            cached = await self.redis_cache.get(AI_BASKET_CACHE_KEY)
            if cached and isinstance(cached, list):
                logger.info(
                    "AI basket cache HIT",
                    symbols=cached,
                    source="cache",
                )
                return cached, f"AIQ ETF top {len(cached)} holdings (cached)"

        # Fetch from ETF if market service available
        if self.market_service:
            try:
                etf_data = await self.market_service.get_etf_profile(AI_ETF_SYMBOL)
                holdings = etf_data.get("holdings", [])

                # Filter for valid US symbols (exclude "n/a" and non-US)
                valid_symbols = []
                for holding in holdings:
                    symbol = holding.get("symbol", "")
                    weight = float(holding.get("weight", 0))

                    # Skip invalid symbols and very small positions
                    if symbol and symbol != "n/a" and weight >= 0.01:
                        valid_symbols.append(symbol)

                    # Stop when we have enough
                    if len(valid_symbols) >= AI_BASKET_TOP_N:
                        break

                if valid_symbols:
                    # Cache the result
                    if self.redis_cache:
                        await self.redis_cache.set(
                            AI_BASKET_CACHE_KEY,
                            valid_symbols,
                            ttl_seconds=AI_BASKET_CACHE_TTL,
                        )

                    logger.info(
                        "AI basket fetched from ETF",
                        etf=AI_ETF_SYMBOL,
                        symbols=valid_symbols,
                        total_holdings=len(holdings),
                    )
                    return valid_symbols, f"AIQ ETF top {len(valid_symbols)} holdings"

            except Exception as e:
                logger.warning(
                    "ETF basket fetch failed, using fallback",
                    etf=AI_ETF_SYMBOL,
                    error=str(e),
                )

        # Fallback to static symbols
        logger.info(
            "Using fallback AI basket",
            symbols=AI_BASKET_FALLBACK,
            reason="ETF fetch unavailable",
        )
        return AI_BASKET_FALLBACK, "Static fallback basket"

    async def calculate_metrics(self) -> list[InsightMetric]:
        """Calculate all 7 AI Sector Risk metrics.

        This method orchestrates the calculation of all metrics,
        handling partial failures gracefully. The AI basket is fetched
        once and reused across all metrics that need it.
        """
        logger.info("Calculating AI Sector Risk metrics")

        # Fetch AI basket once for all metrics that need it
        ai_symbols, basket_source = await self._get_ai_basket_symbols()
        ai_basket = (ai_symbols, basket_source)

        metrics = []

        # Calculate each metric with error handling
        # Metrics that use AI basket receive it as parameter
        metric_calculators: list[tuple[str, Any]] = [
            ("ai_price_anomaly", lambda: self._calculate_ai_price_anomaly(ai_basket)),
            (
                "news_sentiment",
                self._calculate_news_sentiment,
            ),  # Uses topics=technology
            ("smart_money_flow", lambda: self._calculate_smart_money_flow(ai_basket)),
            (
                "options_put_call_ratio",
                lambda: self._calculate_options_put_call_ratio(ai_basket),
            ),
            ("ipo_heat", self._calculate_ipo_heat),
            ("market_liquidity", self._calculate_market_liquidity),
            ("fed_expectations", self._calculate_fed_expectations),
        ]

        for metric_id, calculator in metric_calculators:
            try:
                metric = await calculator()
                metrics.append(metric)
            except Exception as e:
                logger.error(
                    "Metric calculation failed",
                    metric_id=metric_id,
                    error=str(e),
                )
                # Add placeholder metric for failed calculation
                metrics.append(self._create_error_metric(metric_id))

        logger.info(
            "AI Sector Risk metrics calculated",
            metric_count=len(metrics),
            successful=len([m for m in metrics if m.score >= 0]),
        )

        return metrics

    async def _calculate_ai_price_anomaly(
        self, ai_basket: tuple[list[str], str]
    ) -> InsightMetric:
        """Calculate AI Price Anomaly metric using real market data.

        Z-score of AI basket (dynamically sourced from AIQ ETF) vs 200-day SMA.
        Higher Z-score = higher risk of correction.

        Args:
            ai_basket: Tuple of (symbols list, source description) from AIQ ETF
        """
        if not self.market_service:
            return self._create_placeholder_metric(
                "ai_price_anomaly",
                "AI Price Anomaly",
                65.0,
                "Market service not available",
            )

        # Use pre-fetched AI basket
        ai_symbols, basket_source = ai_basket

        z_scores = []
        symbol_data = {}

        for symbol in ai_symbols:
            try:
                # Get daily bars (need 200+ days for SMA calculation)
                df = await self.market_service.get_daily_bars(
                    symbol=symbol,
                    outputsize="full",
                )

                if df is not None and len(df) >= 200:
                    # Calculate 200-day SMA and Z-score
                    close_prices = df["Close"].values
                    current_price = close_prices[-1]
                    sma_200 = np.mean(close_prices[-200:])
                    std_200 = np.std(close_prices[-200:])

                    if std_200 > 0:
                        z_score = (current_price - sma_200) / std_200
                        z_scores.append(z_score)
                        symbol_data[symbol] = {
                            "current": round(current_price, 2),
                            "sma_200": round(sma_200, 2),
                            "z_score": round(z_score, 2),
                        }

            except Exception as e:
                logger.warning(
                    "Failed to get data for symbol",
                    symbol=symbol,
                    error=str(e),
                )

        # Calculate average Z-score and normalize to 0-100
        if z_scores:
            avg_z_score = np.mean(z_scores)
            # Z-score of -2 to +3 maps to 0-100
            score = self.normalize_score(avg_z_score, -2.0, 3.0)
        else:
            score = 50.0
            avg_z_score = 0.0

        status = ThresholdConfig().get_status(score)

        return InsightMetric(
            id="ai_price_anomaly",
            name="AI Price Anomaly",
            score=score,
            status=status,
            explanation=MetricExplanation(
                summary=f"AI stocks are trading {avg_z_score:.1f} standard deviations from average.",
                detail=(
                    f"The AI basket ({', '.join(ai_symbols[:5])}"
                    f"{', ...' if len(ai_symbols) > 5 else ''}) is trading "
                    f"{avg_z_score:.2f} standard deviations {'above' if avg_z_score > 0 else 'below'} "
                    "the 200-day moving average. "
                    f"{'Elevated positioning suggests caution.' if score > 60 else 'Normal range.'}"
                ),
                methodology=(
                    f"Dynamically sources AI stocks from {AI_ETF_SYMBOL} ETF holdings. "
                    "Calculates the Z-score of the equal-weighted AI basket price "
                    "relative to its 200-day simple moving average. Higher Z-scores "
                    "indicate prices extended above historical norms."
                ),
                formula="Z = (P - SMA200) / σ200",
                historical_context=(
                    "Z-scores above 2.0 have historically preceded significant corrections. "
                    f"Current average Z-score: {avg_z_score:.2f}"
                ),
                actionable_insight=(
                    "Consider trimming AI positions if score exceeds 75. "
                    if score > 60
                    else "Current level is within normal range."
                ),
            ),
            data_sources=["TIME_SERIES_DAILY", "ETF_PROFILE"],
            last_updated=datetime.now(UTC),
            raw_data={
                "symbols": ai_symbols,
                "basket_source": basket_source,
                "avg_z_score": round(avg_z_score, 3),
                "symbol_data": symbol_data,
            },
        )

    async def _calculate_news_sentiment(self) -> InsightMetric:
        """Calculate News Sentiment metric using Alpha Vantage NEWS_SENTIMENT.

        Uses topics=technology for broad tech/AI sector sentiment coverage.
        Single API call for efficiency.
        """
        if not self.market_service:
            return self._create_placeholder_metric(
                "news_sentiment",
                "News Sentiment",
                58.0,
                "Market service not available",
            )

        try:
            # Use topics=technology for broad AI/tech sector sentiment
            # This is ONE API call instead of 10 individual ticker calls
            news_data = await self.market_service.get_news_sentiment(
                topics="technology",
                limit=50,
            )

            articles = news_data.get("feed", [])
            if not articles:
                return self._create_placeholder_metric(
                    "news_sentiment",
                    "News Sentiment",
                    50.0,
                    "No technology news articles found",
                )

            # Calculate average sentiment from all articles
            sentiments = [
                float(a["overall_sentiment_score"])
                for a in articles
                if "overall_sentiment_score" in a
            ]

            if not sentiments:
                return self._create_placeholder_metric(
                    "news_sentiment",
                    "News Sentiment",
                    50.0,
                    "No sentiment scores in articles",
                )

            avg_sentiment = float(np.mean(sentiments))
            # Sentiment ranges from -0.35 (bearish) to +0.35 (bullish)
            # Normalize to 0-100 where higher = more euphoric (bullish)
            score = self.normalize_score(avg_sentiment, -0.35, 0.35)

            status = ThresholdConfig().get_status(score)

            return InsightMetric(
                id="news_sentiment",
                name="News Sentiment",
                score=score,
                status=status,
                explanation=MetricExplanation(
                    summary=f"Tech sector news sentiment is {'positive' if avg_sentiment > 0 else 'negative'} ({avg_sentiment:.3f}).",
                    detail=(
                        f"Analyzed {len(articles)} technology sector articles. "
                        f"Average sentiment: {avg_sentiment:.3f}. "
                        f"{'Elevated optimism may signal bubble risk.' if score > 65 else 'Sentiment within normal range.'}"
                    ),
                    methodology=(
                        "Aggregates sentiment from NEWS_SENTIMENT API using topics=technology "
                        "for broad tech/AI sector coverage. Single API call for efficiency. "
                        "Normalizes the -0.35 to +0.35 range to 0-100."
                    ),
                    formula="Score = ((avg_sentiment + 0.35) / 0.70) × 100",
                    historical_context=(
                        "Peak euphoria readings (80+) were seen during ChatGPT launch. "
                        f"Current reading: {score:.1f}"
                    ),
                    actionable_insight=(
                        "Watch for scores above 70 which historically precede pullbacks."
                        if score < 70
                        else "High sentiment suggests caution."
                    ),
                ),
                data_sources=["NEWS_SENTIMENT"],
                last_updated=datetime.now(UTC),
                raw_data={
                    "avg_sentiment": round(avg_sentiment, 4),
                    "article_count": len(articles),
                    "topic": "technology",
                },
            )

        except Exception as e:
            logger.error("News sentiment calculation failed", error=str(e))
            return self._create_placeholder_metric(
                "news_sentiment",
                "News Sentiment",
                50.0,
                f"Error: {str(e)}",
            )

    async def _calculate_smart_money_flow(
        self, ai_basket: tuple[list[str], str]
    ) -> InsightMetric:
        """Calculate Smart Money Flow using Smart Money Index (SMI) logic.

        Smart Money Index (SMI) measures the divergence between "dumb money"
        (first hour trading, driven by emotion/news) and "smart money"
        (last hour trading, driven by institutional positioning).

        Formula: SMI = Last Hour Return - First Hour Return
        - Positive SMI: Smart money buying into close (Bullish)
        - Negative SMI: Smart money selling into close (Bearish)

        Args:
            ai_basket: Tuple of (symbols list, source description) from AIQ ETF
        """
        if not self.market_service:
            return self._create_placeholder_metric(
                "smart_money_flow",
                "Smart Money Flow",
                52.0,
                "Market service not available",
            )

        try:
            # Use pre-fetched AI basket
            ai_symbols, _ = ai_basket
            symbols_to_analyze = ai_symbols[:3]  # Analyze top 3 holdings
            smi_values = []

            for symbol in symbols_to_analyze:
                # Get intraday bars (60min to isolate first/last hour)
                # We need enough data to cover the current/last trading session
                df = await self.market_service.get_intraday_bars(
                    symbol=symbol,
                    interval="60min",
                    outputsize="compact",  # Latest 100 points
                )

                if df is not None and not df.empty:
                    # Group by date to get daily sessions
                    # df index is timezone aware (America/New_York)
                    last_date = df.index[-1].date()
                    todays_bars = df[df.index.date == last_date]

                    if len(todays_bars) >= 2:
                        # First hour bar (9:30 - 10:30)
                        first_hour = todays_bars.iloc[0]
                        # Last hour bar (15:30 - 16:00/16:30)
                        last_hour = todays_bars.iloc[-1]

                        # Calculate returns
                        # (Close - Open) / Open
                        first_hour_return = (
                            (first_hour["Close"] - first_hour["Open"])
                            / first_hour["Open"]
                        ) * 100

                        last_hour_return = (
                            (last_hour["Close"] - last_hour["Open"]) / last_hour["Open"]
                        ) * 100

                        # SMI = Last Hour - First Hour
                        # If Last Hour (Smart) > First Hour (Dumb) -> Positive SMI (Bullish)
                        smi = last_hour_return - first_hour_return
                        smi_values.append(smi)

            if smi_values:
                avg_smi = float(np.mean(smi_values))
                # SMI typically ranges from -2% to +2%
                # Map to 0-100 score where higher is more bullish (smart money buying)
                # But risk metric is "High Risk", so we invert:
                # High SMI (Bullish) = Low Risk Score
                # Low SMI (Bearish/Distribution) = High Risk Score

                # Normalization:
                # SMI = +1.0% -> Score 25 (Low Risk)
                # SMI = 0.0% -> Score 50 (Neutral)
                # SMI = -1.0% -> Score 75 (High Risk)
                score = self.normalize_score(-avg_smi, -1.0, 1.0)
            else:
                avg_smi = 0.0
                score = 50.0

            status = ThresholdConfig().get_status(score)

            return InsightMetric(
                id="smart_money_flow",
                name="Smart Money Flow",
                score=score,
                status=status,
                explanation=MetricExplanation(
                    summary=f"Smart Money Index is {avg_smi:+.2f}% (Last Hour vs First Hour).",
                    detail=(
                        f"Average SMI: {avg_smi:+.2f}%. "
                        f"{'Smart money is buying into the close (bullish).' if avg_smi > 0 else 'Smart money is selling into the close (bearish).'}"
                    ),
                    methodology=(
                        "Calculates Smart Money Index (SMI) = Last Hour Return - First Hour Return. "
                        "Positive SMI indicates institutional accumulation (smart money) vs retail reaction (dumb money). "
                        "Inverted for risk scoring: Negative SMI = High Risk."
                    ),
                    formula="Score = 50 + ((-SMI) / 1.0) × 25",
                    historical_context=(
                        "Smart money distribution often precedes trend reversals. "
                        f"Current SMI: {avg_smi:+.2f}%"
                    ),
                    actionable_insight=(
                        "Institutional distribution detected - caution warranted."
                        if avg_smi < -0.5
                        else "Smart money accumulation supports the trend."
                    ),
                ),
                data_sources=["TIME_SERIES_INTRADAY"],
                last_updated=datetime.now(UTC),
                raw_data={
                    "avg_smi": round(avg_smi, 3),
                    "symbols_analyzed": symbols_to_analyze,
                },
            )

        except Exception as e:
            logger.error("Smart money flow calculation failed", error=str(e))
            return self._create_placeholder_metric(
                "smart_money_flow",
                "Smart Money Flow",
                50.0,
                f"Error: {str(e)}",
            )

    async def _calculate_options_put_call_ratio(
        self, ai_basket: tuple[list[str], str]
    ) -> InsightMetric:
        """Calculate Options Put/Call Ratio using cached per-symbol PCR data.

        Uses DataManager.get_symbol_pcr() for cached, reusable PCR calculations.
        This is a CONTRARIAN indicator:
        - Low PCR (< 0.5) = High Risk (too many calls, euphoria)
        - High PCR (> 1.0) = Low Risk (too many puts, fear)

        Story 2.8: Reusable PCR Service
        - Uses DataManager for cached per-symbol PCR (1-hour TTL)
        - Same calculation reused by AI agent tools
        - Expands from 3 to 10 symbols for better market picture

        Args:
            ai_basket: Tuple of (symbols list, source description)

        Returns:
            InsightMetric with PCR score (contrarian: low PCR = high risk)
        """
        if not self.market_service or not self.redis_cache:
            return self._create_placeholder_metric(
                "options_put_call_ratio",
                "Options Put/Call Ratio",
                50.0,
                "Market service or Redis cache not available",
            )

        # Create DataManager for cached PCR calculations
        data_manager = DataManager(
            redis_cache=self.redis_cache,
            alpha_vantage_service=self.market_service,
        )

        # Use top 10 AI basket symbols for broader market picture (Story 2.8)
        ai_symbols, basket_source = ai_basket
        symbols_to_analyze = ai_symbols[:10]

        total_put_notional = 0.0
        total_call_notional = 0.0
        symbol_details = {}
        contracts_analyzed = 0
        successful_symbols = []

        # Fetch PCR for each symbol using cached service
        for symbol in symbols_to_analyze:
            try:
                pcr_data = await data_manager.get_symbol_pcr(symbol)

                if pcr_data is None:
                    logger.debug(
                        "PCR data not available for symbol",
                        symbol=symbol,
                    )
                    continue

                # Aggregate notionals (convert from millions back to raw)
                total_put_notional += pcr_data.put_notional_mm * 1_000_000
                total_call_notional += pcr_data.call_notional_mm * 1_000_000
                contracts_analyzed += pcr_data.contracts_analyzed
                successful_symbols.append(symbol)

                symbol_details[symbol] = {
                    "current_price": pcr_data.current_price,
                    "atm_zone": f"${pcr_data.atm_zone_low:.2f} - ${pcr_data.atm_zone_high:.2f}",
                    "put_notional_mm": pcr_data.put_notional_mm,
                    "call_notional_mm": pcr_data.call_notional_mm,
                    "contracts_used": pcr_data.contracts_analyzed,
                    "symbol_pcr": pcr_data.pcr,
                }

            except Exception as e:
                logger.warning(
                    "Failed to get PCR for symbol",
                    symbol=symbol,
                    error=str(e),
                )

        # Calculate aggregate PCR
        if total_call_notional > 0:
            pcr = total_put_notional / total_call_notional
        else:
            pcr = 1.0  # Neutral if no call data

        # Normalize to score (CONTRARIAN/INVERTED):
        # PCR 0.3 → Score 95 (High Risk - extreme call buying)
        # PCR 0.7 → Score 60 (Elevated)
        # PCR 1.0 → Score 30 (Normal)
        # PCR 1.3 → Score 5 (Low Risk - extreme put buying)
        score = self.normalize_score(pcr, 0.3, 1.3, invert=True)

        status = ThresholdConfig().get_status(score)

        # Generate interpretation
        if pcr < 0.5:
            pcr_interpretation = "Extreme call buying indicates euphoria"
        elif pcr < 0.7:
            pcr_interpretation = "Elevated call activity suggests optimism"
        elif pcr < 1.0:
            pcr_interpretation = "Near-neutral positioning"
        else:
            pcr_interpretation = "Put buying indicates caution/hedging"

        return InsightMetric(
            id="options_put_call_ratio",
            name="Options Put/Call Ratio",
            score=score,
            status=status,
            explanation=MetricExplanation(
                summary=f"ATM Dollar-Weighted PCR is {pcr:.2f}. {pcr_interpretation}.",
                detail=(
                    f"Put/Call Ratio: {pcr:.2f} (Put Notional: ${total_put_notional / 1_000_000:.1f}M, "
                    f"Call Notional: ${total_call_notional / 1_000_000:.1f}M). "
                    f"Analyzed {contracts_analyzed} ATM contracts across {len(successful_symbols)} symbols. "
                    f"{'Low PCR indicates excessive optimism - contrarian bearish signal.' if pcr < 0.7 else 'PCR within normal range.'}"
                ),
                methodology=(
                    "Calculates ATM Dollar-Weighted Put/Call Ratio using cached per-symbol PCR data. "
                    "Filters: ATM zone (±15%), min premium $0.50, min OI 500. "
                    "Notional = OI × Price × 100. "
                    "CONTRARIAN: Low PCR (call-heavy) = High Risk."
                ),
                formula="PCR = Σ(Put Notionals) / Σ(Call Notionals)",
                historical_context=(
                    "PCR below 0.5 preceded corrections in 2000, 2007, 2021. "
                    f"Current PCR: {pcr:.2f}"
                ),
                actionable_insight=(
                    "Extreme call positioning suggests caution - consider hedging."
                    if pcr < 0.5
                    else "Options positioning within normal parameters."
                ),
            ),
            data_sources=["HISTORICAL_OPTIONS", "GLOBAL_QUOTE"],
            last_updated=datetime.now(UTC),
            raw_data={
                "pcr": round(pcr, 3),
                "total_put_notional_mm": round(total_put_notional / 1_000_000, 2),
                "total_call_notional_mm": round(total_call_notional / 1_000_000, 2),
                "contracts_analyzed": contracts_analyzed,
                "symbols_analyzed": successful_symbols,
                "symbol_details": symbol_details,
                "basket_source": basket_source,
            },
        )

    async def _calculate_ipo_heat(self) -> InsightMetric:
        """Calculate IPO Heat using IPO_CALENDAR endpoint."""
        if not self.market_service:
            return self._create_placeholder_metric(
                "ipo_heat",
                "IPO Heat",
                35.0,
                "Market service not available",
            )

        try:
            ipos = await self.market_service.get_ipo_calendar()

            # Filter for IPOs in next 90 days
            cutoff_date = datetime.now(UTC) + timedelta(days=90)
            upcoming_ipos = []

            for ipo in ipos:
                ipo_date_str = ipo.get("ipoDate", "")
                if ipo_date_str:
                    try:
                        ipo_date = datetime.strptime(ipo_date_str, "%Y-%m-%d")
                        ipo_date = ipo_date.replace(tzinfo=UTC)
                        if ipo_date <= cutoff_date:
                            upcoming_ipos.append(ipo)
                    except ValueError:
                        pass

            ipo_count = len(upcoming_ipos)

            # 0-5 IPOs = cool, 20+ = overheated
            score = self.normalize_score(ipo_count, 0, 25)
            status = ThresholdConfig().get_status(score)

            return InsightMetric(
                id="ipo_heat",
                name="IPO Heat",
                score=score,
                status=status,
                explanation=MetricExplanation(
                    summary=f"{ipo_count} IPOs scheduled in next 90 days.",
                    detail=(
                        f"There are {ipo_count} IPOs scheduled in the next 90 days. "
                        f"{'High IPO activity suggests companies rushing to market.' if ipo_count > 15 else 'Normal IPO activity.'}"
                    ),
                    methodology=(
                        "Counts scheduled IPOs from IPO_CALENDAR endpoint. "
                        "Normalizes based on historical ranges: <5 = cold, >20 = overheated."
                    ),
                    formula="Score = min(100, (IPO_count / 25) × 100)",
                    historical_context=(
                        "Peak readings (80+) occurred in late 2021 with 25+ IPOs per quarter. "
                        f"Current count: {ipo_count}"
                    ),
                    actionable_insight=(
                        "Normal IPO activity suggests healthy market conditions."
                        if ipo_count < 15
                        else "Elevated IPO activity may signal late-cycle behavior."
                    ),
                ),
                data_sources=["IPO_CALENDAR"],
                last_updated=datetime.now(UTC),
                raw_data={
                    "ipo_count_90d": ipo_count,
                    "total_ipos": len(ipos),
                },
            )

        except Exception as e:
            logger.error("IPO heat calculation failed", error=str(e))
            return self._create_placeholder_metric(
                "ipo_heat",
                "IPO Heat",
                35.0,
                f"Error: {str(e)}",
            )

    async def _calculate_market_liquidity(self) -> InsightMetric:
        """Calculate Market Liquidity metric using FRED API data.

        Uses three FRED indicators to measure actual market liquidity:
        1. RRP Balance (50% weight): High RRP = abundant liquidity = HIGH bubble risk
        2. SOFR-EFFR Spread (30% weight): Low spread = no stress = bubble can form
        3. RRP 20-day Trend (20% weight): Rising RRP = increasing liquidity

        Theory: "When capital is abundant, asset prices easily rise and bubbles can form.
        When capital is tight, even with high market sentiment, bubbles cannot easily form."
        """
        if not self.fred_service:
            return self._create_placeholder_metric(
                "market_liquidity",
                "Market Liquidity",
                50.0,
                "FRED service not available",
            )

        try:
            # Fetch FRED data concurrently (60 days for trend calculation)
            sofr_df, effr_df, rrp_df = await asyncio.gather(
                self.fred_service.get_sofr(days=60),
                self.fred_service.get_effr(days=60),
                self.fred_service.get_rrp_balance(days=60),
            )

            # Check data availability
            if sofr_df.empty or effr_df.empty or rrp_df.empty:
                return self._create_placeholder_metric(
                    "market_liquidity",
                    "Market Liquidity",
                    50.0,
                    "Insufficient FRED data",
                )

            # Extract latest values
            sofr_current = float(sofr_df["value"].iloc[-1])
            effr_current = float(effr_df["value"].iloc[-1])
            rrp_current = float(rrp_df["value"].iloc[-1])

            # --- Component 1: RRP Balance Score (50% weight) ---
            # RRP ranges: 0 (tight) to peak (extreme liquidity)
            # Higher RRP = more liquidity = higher bubble risk
            rrp_score = self.normalize_score(rrp_current, 0, RRP_PEAK_BILLIONS)

            # --- Component 2: SOFR-EFFR Spread Score (30% weight) ---
            # Normal: SOFR slightly above EFFR (5-15 bps)
            # Stress: SOFR spikes above EFFR (>50 bps) = funding stress
            sofr_effr_spread = (sofr_current - effr_current) * 100  # Convert to bps

            # Inverted: Low spread (normal conditions) = bubble can form = HIGH score
            # High spread (stress) = no bubble risk = LOW score
            spread_score = self.normalize_score(
                sofr_effr_spread, 0, SPREAD_STRESS_THRESHOLD_BPS, invert=True
            )

            # --- Component 3: RRP 20-day Trend Score (20% weight) ---
            # Rising RRP = increasing liquidity = higher bubble risk
            if len(rrp_df) >= 20:
                rrp_20d_ago = float(rrp_df["value"].iloc[-20])
                rrp_change = rrp_current - rrp_20d_ago
                rrp_change_pct = (
                    (rrp_change / rrp_20d_ago * 100) if rrp_20d_ago > 0 else 0
                )
            else:
                rrp_change = 0.0
                rrp_change_pct = 0.0
                rrp_20d_ago = rrp_current

            # Trend: Rising RRP = higher risk
            trend_score = self.normalize_score(
                rrp_change_pct, -RRP_TREND_CHANGE_RANGE_PCT, RRP_TREND_CHANGE_RANGE_PCT
            )

            # --- Weighted Composite Score ---
            # RRP Level: 50%, SOFR-EFFR Spread: 30%, RRP Trend: 20%
            final_score = rrp_score * 0.5 + spread_score * 0.3 + trend_score * 0.2
            final_score = round(final_score, 2)

            status = ThresholdConfig().get_status(final_score)

            # Generate interpretation
            if rrp_current > 1000:
                liquidity_level = "abundant"
            elif rrp_current > 300:
                liquidity_level = "moderate"
            else:
                liquidity_level = "tight"

            return InsightMetric(
                id="market_liquidity",
                name="Market Liquidity",
                score=final_score,
                status=status,
                explanation=MetricExplanation(
                    summary=f"Market liquidity is {liquidity_level}. RRP: ${rrp_current:.0f}B, SOFR-EFFR: {sofr_effr_spread:.0f}bps.",
                    detail=(
                        f"Fed RRP Balance: ${rrp_current:.1f}B (vs peak $2,500B in Dec 2022). "
                        f"SOFR: {sofr_current:.2f}%, EFFR: {effr_current:.2f}% (spread: {sofr_effr_spread:.0f}bps). "
                        f"20-day RRP change: {rrp_change:+.1f}B ({rrp_change_pct:+.1f}%). "
                        f"{'Abundant liquidity supports bubble formation.' if final_score > 60 else 'Tight liquidity constrains bubble risk.'}"
                    ),
                    methodology=(
                        "Uses FRED API for actual liquidity metrics: "
                        "RRP Balance (50% weight) measures excess system liquidity, "
                        "SOFR-EFFR spread (30% weight) measures funding stress, "
                        "RRP trend (20% weight) measures liquidity momentum. "
                        "Theory: Bubbles require abundant capital to form."
                    ),
                    formula="Score = 0.5×RRP_score + 0.3×Spread_score + 0.2×Trend_score",
                    historical_context=(
                        f"Peak RRP: ${RRP_PEAK_BILLIONS:,}B (Dec 2022 - extreme liquidity). "
                        f"Current RRP: ${rrp_current:.0f}B ({rrp_current / RRP_PEAK_BILLIONS * 100:.1f}% of peak). "
                        f"Low RRP historically coincides with market stress periods."
                    ),
                    actionable_insight=(
                        "Abundant liquidity supports risk assets - watch for euphoria."
                        if final_score > 60
                        else "Tight liquidity constrains bubble formation - stay vigilant for stress signals."
                    ),
                ),
                data_sources=["FRED_SOFR", "FRED_EFFR", "FRED_RRP"],
                last_updated=datetime.now(UTC),
                raw_data={
                    "sofr_current": round(sofr_current, 3),
                    "effr_current": round(effr_current, 3),
                    "sofr_effr_spread_bps": round(sofr_effr_spread, 1),
                    "rrp_current_billions": round(rrp_current, 1),
                    "rrp_20d_ago_billions": round(rrp_20d_ago, 1),
                    "rrp_change_billions": round(rrp_change, 1),
                    "rrp_change_pct": round(rrp_change_pct, 2),
                    "component_scores": {
                        "rrp_level": round(rrp_score, 2),
                        "sofr_effr_spread": round(spread_score, 2),
                        "rrp_trend": round(trend_score, 2),
                    },
                    "weights": {
                        "rrp_level": 0.5,
                        "sofr_effr_spread": 0.3,
                        "rrp_trend": 0.2,
                    },
                },
            )

        except Exception as e:
            logger.error("Market liquidity calculation failed", error=str(e))
            return self._create_placeholder_metric(
                "market_liquidity",
                "Market Liquidity",
                50.0,
                f"Error: {str(e)}",
            )

    async def _calculate_fed_expectations(self) -> InsightMetric:
        """Calculate Fed Expectations using 2Y yield slope."""
        if not self.market_service:
            return self._create_placeholder_metric(
                "fed_expectations",
                "Fed Expectations",
                62.0,
                "Market service not available",
            )

        try:
            # Get 2Y yield history
            yield_2y_df = await self.market_service.get_treasury_yield(
                maturity="2year",
                interval="daily",
            )

            if yield_2y_df.empty or len(yield_2y_df) < 20:
                return self._create_placeholder_metric(
                    "fed_expectations",
                    "Fed Expectations",
                    50.0,
                    "Insufficient yield data",
                )

            # Calculate 20-day change
            current_yield = yield_2y_df["value"].iloc[-1]
            yield_20d_ago = (
                yield_2y_df["value"].iloc[-20]
                if len(yield_2y_df) >= 20
                else yield_2y_df["value"].iloc[0]
            )
            change_20d = current_yield - yield_20d_ago

            # Falling yields = rate cut expectations = risk-on
            # Change from -0.5% (dovish) to +0.5% (hawkish) maps to 0-100
            # Invert: falling yields (negative change) = higher score
            score = self.normalize_score(-change_20d, -0.5, 0.5)
            status = ThresholdConfig().get_status(score)

            return InsightMetric(
                id="fed_expectations",
                name="Fed Expectations",
                score=score,
                status=status,
                explanation=MetricExplanation(
                    summary=f"2Y yield changed {change_20d:+.2f}% over 20 days.",
                    detail=(
                        f"2-year yield: {current_yield:.2f}% (was {yield_20d_ago:.2f}% 20 days ago). "
                        f"{'Falling yields suggest rate cut expectations, supporting risk assets.' if change_20d < 0 else 'Rising yields indicate hawkish expectations.'}"
                    ),
                    methodology=(
                        "Measures the 20-day change in the 2-year Treasury yield. "
                        "Declining yields indicate dovish expectations, rising yields hawkish."
                    ),
                    formula="Score = 50 + (Δ2Y_20d / -0.5) × 50",
                    historical_context=(
                        "Sharp yield declines preceded major rallies in 2023. "
                        f"Current 20-day change: {change_20d:+.2f}%"
                    ),
                    actionable_insight=(
                        "Dovish expectations are priced in - supports risk assets."
                        if change_20d < -0.1
                        else "Neutral or hawkish expectations."
                    ),
                ),
                data_sources=["TREASURY_YIELD"],
                last_updated=datetime.now(UTC),
                raw_data={
                    "yield_2y_current": round(current_yield, 3),
                    "yield_2y_20d_ago": round(yield_20d_ago, 3),
                    "change_20d": round(change_20d, 3),
                },
            )

        except Exception as e:
            logger.error("Fed expectations calculation failed", error=str(e))
            return self._create_placeholder_metric(
                "fed_expectations",
                "Fed Expectations",
                50.0,
                f"Error: {str(e)}",
            )

    def _create_placeholder_metric(
        self,
        metric_id: str,
        name: str,
        score: float,
        reason: str,
    ) -> InsightMetric:
        """Create a placeholder metric with a default score."""
        status = ThresholdConfig().get_status(score)

        return InsightMetric(
            id=metric_id,
            name=name,
            score=score,
            status=status,
            explanation=MetricExplanation(
                summary=f"Using estimated value. {reason}",
                detail=(
                    f"Real-time calculation unavailable. Using estimated score of {score:.1f}. "
                    f"Reason: {reason}"
                ),
                methodology="Placeholder - real calculation pending.",
                historical_context="Historical data unavailable.",
                actionable_insight="Wait for real-time data for accurate insights.",
            ),
            data_sources=[],
            last_updated=datetime.now(UTC),
            raw_data={"placeholder": True, "reason": reason},
        )

    def _create_error_metric(self, metric_id: str) -> InsightMetric:
        """Create placeholder metric when calculation fails."""
        metric_defs = {d["id"]: d for d in self.get_metric_definitions()}
        metric_def = metric_defs.get(
            metric_id, {"name": metric_id.replace("_", " ").title()}
        )

        return InsightMetric(
            id=metric_id,
            name=metric_def.get("name", metric_id),
            score=-1,  # Sentinel value for error
            status=MetricStatus.NORMAL,
            explanation=MetricExplanation(
                summary="Data temporarily unavailable.",
                detail=(
                    "Unable to calculate this metric due to data availability issues. "
                    "Please try refreshing in a few minutes."
                ),
                methodology="Unable to retrieve calculation methodology.",
                historical_context="Historical data unavailable.",
                actionable_insight="No actionable insight available at this time.",
            ),
            data_sources=metric_def.get("data_sources", []),
            last_updated=datetime.now(UTC),
            raw_data={"error": True, "metric_id": metric_id},
        )

    def _generate_composite_interpretation(
        self,
        score: float,
        status: MetricStatus,
    ) -> str:
        """Generate AI-specific composite interpretation."""
        if status == MetricStatus.LOW:
            return (
                f"AI Sector Risk Index: {score:.1f}/100 (Low Risk). "
                "Fear and pessimism dominate. Historically a good accumulation zone. "
                "Consider building positions in quality AI names."
            )
        elif status == MetricStatus.NORMAL:
            return (
                f"AI Sector Risk Index: {score:.1f}/100 (Normal). "
                "The AI sector is in a healthy bull market phase. "
                "Standard position sizing appropriate."
            )
        elif status == MetricStatus.ELEVATED:
            return (
                f"AI Sector Risk Index: {score:.1f}/100 (Elevated). "
                "Caution warranted. Late-cycle dynamics may be emerging. "
                "Consider trimming positions and tightening stops."
            )
        else:  # HIGH
            return (
                f"AI Sector Risk Index: {score:.1f}/100 (High Risk). "
                "Euphoria indicators are flashing. Historical parallels suggest "
                "elevated correction risk. Defensive positioning recommended."
            )
