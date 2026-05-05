"""
Stochastic Oscillator analysis engine.
Provides technical analysis using the Stochastic Oscillator to identify overbought/oversold conditions,
crossover signals, and potential reversals in stock price movements.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import pandas as pd
import structlog
from scipy.signal import find_peaks

from ...api.models import StochasticAnalysisResponse, StochasticLevel

if TYPE_CHECKING:
    from ...services.data_manager import DataManager

logger = structlog.get_logger()


class StochasticAnalyzer:
    """Stochastic Oscillator technical analysis engine."""

    def __init__(self, data_manager: "DataManager"):
        """
        Initialize analyzer with DataManager for cached OHLCV access.

        Args:
            data_manager: DataManager for all market data (uses Redis caching for daily+)
        """
        self.data_manager = data_manager
        self.data: pd.DataFrame | None = None
        self.symbol: str = ""
        self.timeframe: str = "1d"

    async def analyze(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        timeframe: str = "1d",
        k_period: int = 14,
        d_period: int = 3,
    ) -> StochasticAnalysisResponse:
        """
        Perform Stochastic Oscillator analysis.

        Args:
            symbol: Stock symbol to analyze
            start_date: Start date for analysis (YYYY-MM-DD format)
            end_date: End date for analysis (YYYY-MM-DD format)
            timeframe: Timeframe for analysis ('1h', '1d', '1w', '1M')
            k_period: Period for %K calculation (default 14)
            d_period: Period for %D calculation (default 3)

        Returns:
            StochasticAnalysisResponse with complete stochastic analysis
        """
        try:
            logger.info(
                "Starting stochastic oscillator analysis",
                symbol=symbol,
                timeframe=timeframe,
                k_period=k_period,
                d_period=d_period,
            )

            self.symbol = symbol.upper()
            self.timeframe = timeframe

            # Fetch stock data
            stock_data = await self._fetch_stock_data(start_date, end_date)
            if stock_data is None or stock_data.empty:
                raise ValueError(
                    f"'{symbol}' is not a valid stock symbol or the stock may be delisted."
                )

            self.data = stock_data

            # Calculate stochastic oscillator
            stoch_data = self._calculate_stochastic(stock_data, k_period, d_period)

            if stoch_data.empty:
                raise ValueError("Insufficient data for stochastic calculation.")

            # Get current values
            current_price = float(stoch_data["Close"].iloc[-1])
            current_k = float(stoch_data["slow_%k"].iloc[-1])
            current_d = float(stoch_data["slow_%d"].iloc[-1])

            # Determine current signal
            current_signal = self._determine_signal(current_k)

            # Analyze signals and patterns
            signal_changes = self._analyze_crossovers(stoch_data)
            overbought_oversold_status = self._analyze_overbought_oversold(stoch_data)
            divergence_analysis = self._analyze_divergence(stoch_data)

            # Build stochastic levels history (last 30 data points for performance)
            stochastic_levels = self._build_stochastic_levels(stoch_data.tail(30))

            # Generate insights
            analysis_summary, key_insights = self._generate_stochastic_insights(
                stoch_data,
                current_k,
                current_d,
                current_signal,
                signal_changes,
                overbought_oversold_status,
                divergence_analysis,
            )

            # Build raw data for debugging and advanced features
            raw_data = self._build_raw_data(stoch_data, k_period, d_period, timeframe)

            response = StochasticAnalysisResponse(
                symbol=self.symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
                current_price=current_price,
                analysis_date=datetime.now().isoformat(),
                k_period=k_period,
                d_period=d_period,
                current_k=current_k,
                current_d=current_d,
                current_signal=current_signal,
                stochastic_levels=stochastic_levels,
                signal_changes=signal_changes,
                analysis_summary=analysis_summary,
                key_insights=key_insights,
                raw_data=raw_data,
            )

            logger.info(
                "Stochastic oscillator analysis completed",
                symbol=self.symbol,
                current_signal=current_signal,
                k_value=current_k,
                d_value=current_d,
            )

            return response

        except Exception as e:
            logger.error("Stochastic analysis failed", symbol=symbol, error=str(e))
            raise

    async def _fetch_stock_data(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame:
        """
        Fetch stock data via DataManager (with Redis caching for daily+).

        DataManager handles all granularities:
        - Intraday (1min-15min): No cache, always fresh
        - 30min-60min: Short TTL (5-15 min)
        - Daily+: Standard TTL (1-4 hours)
        """
        try:

            # Map timeframe to DataManager granularity
            granularity_map = {
                "1h": "60min",
                "1d": "daily",
                "1w": "weekly",
                "1M": "monthly",
            }
            granularity = granularity_map.get(self.timeframe, "daily")

            logger.info(
                "Fetching OHLCV via DataManager",
                symbol=self.symbol,
                granularity=granularity,
            )

            ohlcv_list = await self.data_manager.get_ohlcv(
                symbol=self.symbol,
                granularity=granularity,
                outputsize="compact",  # 6 months is sufficient for stochastic
            )

            if not ohlcv_list:
                logger.error("No data returned from DataManager", symbol=self.symbol)
                return pd.DataFrame()

            # Convert OHLCVData list to DataFrame
            data = pd.DataFrame(
                [
                    {
                        "Open": d.open,
                        "High": d.high,
                        "Low": d.low,
                        "Close": d.close,
                        "Volume": d.volume,
                    }
                    for d in ohlcv_list
                ],
                # `pd.to_datetime(..., utc=True)` normalizes a list that may mix
                # naive and tz-aware datetimes (e.g. old cache entries vs fresh
                # yfinance pulls) into a single UTC-aware DatetimeIndex.
                index=pd.to_datetime([d.date for d in ohlcv_list], utc=True),
            )

            # Sort by date ascending (oldest first) for stochastic calculation
            data = data.sort_index()

            # Apply date filters if provided
            if start_date:
                start_dt = pd.Timestamp(start_date, tz=UTC)
                data = data[data.index >= start_dt]

            if end_date:
                end_dt = pd.Timestamp(end_date, tz=UTC)
                data = data[data.index <= end_dt]

            logger.info(
                "Fetched stock data via DataManager",
                symbol=self.symbol,
                timeframe=self.timeframe,
                granularity=granularity,
                data_points=len(data),
                start=data.index[0] if len(data) > 0 else None,
                end=data.index[-1] if len(data) > 0 else None,
            )

            return data.dropna()

        except Exception as e:
            logger.error("Failed to fetch stock data", symbol=self.symbol, error=str(e))
            raise

    def _calculate_stochastic(
        self,
        data: pd.DataFrame,
        k_period: int = 14,
        d_period: int = 3,
        slow_k_period: int = 3,
    ) -> pd.DataFrame:
        """
        Calculate the Fast and Slow Stochastic Oscillator.
        The Slow %K is a smoothed version of the Fast %K, which reduces false signals.
        """
        df = data.copy()

        # Handle empty DataFrame
        if df.empty or not all(col in df.columns for col in ["High", "Low", "Close"]):
            return pd.DataFrame()

        # Calculate Highs and Lows for the look-back period
        low_min = df["Low"].rolling(window=k_period).min()
        high_max = df["High"].rolling(window=k_period).max()

        # Calculate Fast %K
        df["fast_%k"] = 100 * (df["Close"] - low_min) / (high_max - low_min)

        # Calculate Slow %K (which is a 3-period SMA of Fast %K)
        df["slow_%k"] = df["fast_%k"].rolling(window=slow_k_period).mean()

        # Calculate Slow %D (which is a 3-period SMA of Slow %K)
        df["slow_%d"] = df["slow_%k"].rolling(window=d_period).mean()

        return df.dropna()

    def _determine_signal(
        self, k_value: float
    ) -> Literal["overbought", "oversold", "neutral"]:
        """Determine the current overbought/oversold signal."""
        if k_value >= 80:
            return "overbought"
        elif k_value <= 20:
            return "oversold"
        else:
            return "neutral"

    def _analyze_overbought_oversold(self, data: pd.DataFrame) -> dict[str, Any]:
        """
        Analyze the current overbought/oversold status.
        Flags potential reversals when the oscillator exits these zones.
        """
        latest = data.iloc[-1]
        previous = data.iloc[-2] if len(data) >= 2 else latest

        reversal_signals: list[dict[str, str]] = []
        status: dict[str, Any] = {
            "current_status": self._determine_signal(latest["slow_%k"]),
            "k_value": float(latest["slow_%k"]),
            "d_value": float(latest["slow_%d"]),
            "reversal_signals": reversal_signals,
        }

        # Check for reversals (exiting the zones)
        if previous["slow_%k"] > 80 and latest["slow_%k"] <= 80:
            status["reversal_signals"].append(
                {
                    "type": "exit_overbought",
                    "description": "Potential Reversal Signal: Exiting Overbought zone",
                }
            )

        if previous["slow_%k"] < 20 and latest["slow_%k"] >= 20:
            status["reversal_signals"].append(
                {
                    "type": "exit_oversold",
                    "description": "Potential Reversal Signal: Exiting Oversold zone",
                }
            )

        return status

    def _analyze_crossovers(
        self, data: pd.DataFrame, lookback_days: int = 15
    ) -> list[dict[str, Any]]:
        """
        Identify recent buy and sell signals based on %K and %D crossovers.
        """
        recent_data = data.tail(lookback_days).copy()
        signals = []

        # Shift columns to compare current day with the previous day
        recent_data["prev_k"] = recent_data["slow_%k"].shift(1)
        recent_data["prev_d"] = recent_data["slow_%d"].shift(1)

        # Find Buy Signals: %K crosses above %D
        buy_mask = (recent_data["slow_%k"] > recent_data["slow_%d"]) & (
            recent_data["prev_k"] <= recent_data["prev_d"]
        )
        buy_days = recent_data[buy_mask]

        # Find Sell Signals: %K crosses below %D
        sell_mask = (recent_data["slow_%k"] < recent_data["slow_%d"]) & (
            recent_data["prev_k"] >= recent_data["prev_d"]
        )
        sell_days = recent_data[sell_mask]

        for index, row in buy_days.iterrows():
            signals.append(
                {
                    "type": "buy",
                    "date": index.strftime("%Y-%m-%d"),
                    "k_value": float(row["slow_%k"]),
                    "d_value": float(row["slow_%d"]),
                    "description": f"Buy Signal on {index.date()}",
                }
            )

        for index, row in sell_days.iterrows():
            signals.append(
                {
                    "type": "sell",
                    "date": index.strftime("%Y-%m-%d"),
                    "k_value": float(row["slow_%k"]),
                    "d_value": float(row["slow_%d"]),
                    "description": f"Sell Signal on {index.date()}",
                }
            )

        return sorted(signals, key=lambda x: x["date"])

    def _analyze_divergence(
        self, data: pd.DataFrame, lookback_period: int = 90
    ) -> list[dict[str, Any]]:
        """
        Detect bullish and bearish divergence by comparing price and oscillator peaks/troughs.
        """
        divergences = []
        df = data.tail(lookback_period) if len(data) > lookback_period else data

        try:
            # Find peaks (highs) in price and oscillator
            price_peaks, _ = find_peaks(df["Close"], distance=5)
            osc_peaks, _ = find_peaks(df["slow_%k"], distance=5)

            # Find troughs (lows) by inverting the series
            price_troughs, _ = find_peaks(-df["Close"], distance=5)
            osc_troughs, _ = find_peaks(-df["slow_%k"], distance=5)

            # Check for Bearish Divergence (Higher High in Price, Lower High in Oscillator)
            if len(price_peaks) >= 2 and len(osc_peaks) >= 2:
                last_price_peak = df["Close"].iloc[price_peaks[-1]]
                prev_price_peak = df["Close"].iloc[price_peaks[-2]]

                last_osc_peak = df["slow_%k"].iloc[price_peaks[-1]]
                prev_osc_peak = df["slow_%k"].iloc[price_peaks[-2]]

                if last_price_peak > prev_price_peak and last_osc_peak < prev_osc_peak:
                    divergences.append(
                        {
                            "type": "bearish",
                            "description": "Bearish Divergence Detected: Potential reversal down",
                        }
                    )

            # Check for Bullish Divergence (Lower Low in Price, Higher Low in Oscillator)
            if len(price_troughs) >= 2:
                last_price_trough = df["Close"].iloc[price_troughs[-1]]
                prev_price_trough = df["Close"].iloc[price_troughs[-2]]

                last_osc_trough = df["slow_%k"].iloc[price_troughs[-1]]
                prev_osc_trough = df["slow_%k"].iloc[price_troughs[-2]]

                if (
                    last_price_trough < prev_price_trough
                    and last_osc_trough > prev_osc_trough
                ):
                    divergences.append(
                        {
                            "type": "bullish",
                            "description": "Bullish Divergence Detected: Potential reversal up",
                        }
                    )

        except Exception as e:
            logger.warning("Divergence analysis failed", error=str(e))

        return divergences

    def _build_stochastic_levels(self, data: pd.DataFrame) -> list[StochasticLevel]:
        """Build stochastic levels history for the response."""
        levels: list[StochasticLevel] = []
        for index, row in data.iterrows():
            levels.append(
                StochasticLevel(
                    timestamp=index.strftime("%Y-%m-%d %H:%M:%S"),
                    k_percent=float(row["slow_%k"]),
                    d_percent=float(row["slow_%d"]),
                    signal=self._determine_signal(row["slow_%k"]),
                )
            )
        return levels

    def _generate_stochastic_insights(
        self,
        data: pd.DataFrame,
        current_k: float,
        current_d: float,
        current_signal: str,
        signal_changes: list[dict[str, Any]],
        overbought_oversold: dict[str, Any],
        divergences: list[dict[str, Any]],
    ) -> tuple[str, list[str]]:
        """Generate comprehensive stochastic analysis insights."""

        # Build summary
        signal_desc = {
            "overbought": "potentially overextended and due for a pullback",
            "oversold": "potentially oversold and due for a bounce",
            "neutral": "in a neutral zone with no clear directional bias",
        }

        summary = (
            f"Stochastic oscillator shows %K at {current_k:.1f}% and %D at {current_d:.1f}%, "
            f"indicating the stock is {signal_desc[current_signal]}. "
        )

        recent_signals = [
            s
            for s in signal_changes
            if s["date"] >= (data.index[-1] - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        ]
        if recent_signals:
            summary += f"Recent crossover activity detected with {len(recent_signals)} signal(s) in the past week. "

        if divergences:
            div_types = [d["type"] for d in divergences]
            summary += f"Divergence analysis shows {', '.join(div_types)} patterns suggesting potential reversals. "

        # Build key insights
        insights = [
            f"Current Signal: {current_signal.title()} (%K: {current_k:.1f}%, %D: {current_d:.1f}%)",
            f"Oscillator Position: {'Above' if current_k > current_d else 'Below'} signal line",
        ]

        # Add reversal signals if present
        if overbought_oversold.get("reversal_signals"):
            for signal in overbought_oversold["reversal_signals"]:
                insights.append(signal["description"])

        # Add recent crossovers
        if recent_signals:
            latest_signal = recent_signals[-1]
            insights.append(
                f"Latest Signal: {latest_signal['type'].title()} crossover on {latest_signal['date']}"
            )

        # Add divergence insights
        if divergences:
            for div in divergences:
                insights.append(div["description"])

        return summary, insights

    def _build_raw_data(
        self, data: pd.DataFrame, k_period: int, d_period: int, timeframe: str
    ) -> dict[str, Any]:
        """Build comprehensive raw data for debugging and advanced features."""
        return {
            "timeframe": timeframe,
            "data_points": len(data),
            "date_range": {
                "start": data.index[0].strftime("%Y-%m-%d"),
                "end": data.index[-1].strftime("%Y-%m-%d"),
            },
            "parameters": {
                "k_period": k_period,
                "d_period": d_period,
                "slow_k_period": 3,  # Fixed smoothing period
            },
            "current_levels": {
                "k_percent": float(data["slow_%k"].iloc[-1]),
                "d_percent": float(data["slow_%d"].iloc[-1]),
                "fast_k": (
                    float(data["fast_%k"].iloc[-1])
                    if "fast_%k" in data.columns
                    else None
                ),
            },
            "statistics": {
                "k_mean": float(data["slow_%k"].mean()),
                "k_std": float(data["slow_%k"].std()),
                "d_mean": float(data["slow_%d"].mean()),
                "d_std": float(data["slow_%d"].std()),
                "overbought_count": int((data["slow_%k"] > 80).sum()),
                "oversold_count": int((data["slow_%k"] < 20).sum()),
            },
            "calculation_method": "slow_stochastic_oscillator",
        }
