/**
 * Formatting functions for analysis responses.
 * Converts API responses into markdown for chat display.
 */

import type {
  BalanceSheetResponse,
  CashFlowResponse,
  CompanyOverviewResponse,
  FibonacciAnalysisResponse,
  MacroSentimentResponse,
  MarketMoversResponse,
  NewsSentimentResponse,
  StockFundamentalsResponse,
  StochasticAnalysisResponse,
} from "../../services/analysis";
import { formatDate, formatTimestamp } from "../../utils/timeFormatter";

export function formatFibonacciResponse(
  result: FibonacciAnalysisResponse,
): string {
  // Build trends section
  let trendsSection = "";
  if (result.raw_data?.top_trends && result.raw_data.top_trends.length > 0) {
    const trends = result.raw_data.top_trends.slice(0, 3); // Top 3 trends

    trendsSection = `

### 📊 Key Trends Identified

${trends
  .map((trend: any, index: number) => {
    const trendEmoji = trend.type.includes("Uptrend") ? "📈" : "📉";

    // Calculate Golden Zone (61.8% retracement area) for this trend
    const fibLevels = trend.fibonacci_levels || [];
    const goldenLevel = fibLevels.find((l: any) => l.percentage === "61.8%");
    let goldenZone = "";
    if (goldenLevel) {
      // Golden Zone is typically around 61.8% level (use a small range)
      const lowerBound = goldenLevel.price * 0.995; // -0.5%
      const upperBound = goldenLevel.price * 1.005; // +0.5%
      goldenZone = `\n\n• **Golden Zone**: $${lowerBound.toFixed(2)} - $${upperBound.toFixed(2)}`;
    }

    // Build Fibonacci levels collapsible section
    const fibSection =
      fibLevels.length > 0
        ? `

<details>
<summary><strong>📐 Fibonacci Levels</strong> (expand)</summary>

| Level | Price |
|-------|-------|
${fibLevels.map((level: any) => `| ${level.percentage} | $${level.price.toFixed(2)} |`).join("\n")}

</details>`
        : "";

    return `**${index + 1}. ${trendEmoji} ${trend.type.toUpperCase()}**

• **Period**: ${trend.period}

• **Magnitude**: $${(trend.magnitude || 0).toFixed(2)} move

• **Range**: $${trend.low?.toFixed(2)} → $${trend.high?.toFixed(2)}${goldenZone}${fibSection}`;
  })
  .join("\n\n")}
`;
  }

  return `## 📊 Fibonacci Analysis - ${result.symbol}

### 📋 Summary

• **Trend**: ${result.market_structure.trend_direction.toUpperCase()}

• **Current Price**: $${result.current_price.toFixed(2)}

• **Confidence**: ${(result.confidence_score * 100).toFixed(1)}%

• **Period**: ${result.start_date || "Dynamic"} to ${result.end_date || "Current"}
${trendsSection}
`;
}

export function formatMacroResponse(result: MacroSentimentResponse): string {
  const sentimentEmoji =
    result.market_sentiment.toLowerCase() === "bullish"
      ? "📈"
      : result.market_sentiment.toLowerCase() === "bearish"
        ? "📉"
        : "➡️";

  const allSectors = Object.entries(result.sector_performance)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6);

  return `## 🌍 Macro Market Sentiment

### 📋 Key Metrics

| Metric | Value |
|--------|-------|
| Market Sentiment | ${sentimentEmoji} ${result.market_sentiment.toUpperCase()} |
| VIX Level | ${result.vix_level.toFixed(2)} (${result.vix_interpretation}) |
| Fear/Greed Score | ${result.fear_greed_score}/100 |

### 📝 Market Outlook

${result.market_outlook}

### 📊 Sector Performance

| Sector | Performance |
|--------|-------------|
${allSectors.map(([sector, perf]) => `| ${sector} | ${perf > 0 ? "+" : ""}${perf.toFixed(2)}% |`).join("\n")}

### 🔑 Key Factors
${result.key_factors.map((factor) => `• ${factor}`).join("\n\n")}
`;
}

export function formatFundamentalsResponse(
  result: StockFundamentalsResponse,
  locale: string,
): string {
  const priceChangeEmoji = result.price_change >= 0 ? "📈" : "📉";
  const analysisDate = formatDate(new Date(), locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return `## 💼 Fundamentals - ${result.symbol}
*${result.company_name} • ${analysisDate}*

### 📋 Key Metrics

| Metric | Value |
|--------|-------|
| Current Price | ${priceChangeEmoji} $${result.current_price.toFixed(2)} (${result.price_change >= 0 ? "+" : ""}${result.price_change_percent.toFixed(2)}%) |
| Market Cap | $${(result.market_cap / 1e9).toFixed(2)}B |
${result.pe_ratio ? `| P/E Ratio | ${result.pe_ratio.toFixed(2)} |` : ""}
${result.pb_ratio ? `| P/B Ratio | ${result.pb_ratio.toFixed(2)} |` : ""}

### 📊 Valuation & Trading

${result.beta ? `**Beta** ${result.beta.toFixed(2)} • ` : ""}${result.dividend_yield ? `**Dividend Yield** ${result.dividend_yield.toFixed(2)}% • ` : ""}**Volume** ${result.volume.toLocaleString()} • **Avg Volume** ${result.avg_volume.toLocaleString()}

**52-Week High** $${result.fifty_two_week_high.toFixed(2)} • **52-Week Low** $${result.fifty_two_week_low.toFixed(2)}
`;
}

export function formatStochasticResponse(
  result: StochasticAnalysisResponse,
  locale: string,
): string {
  // Signal interpretation with dynamic color intensity
  let signalMeaning = "";
  let signalColor = ""; // Background color
  let textColor = "white"; // Text color

  const kValue = result.current_k;

  if (result.current_signal === "overbought") {
    // Red background: darker as %K approaches 100
    const intensity = Math.min(((kValue - 80) / 20) * 100, 100); // 0-100%
    const red = Math.round(139 + (intensity / 100) * 116); // 139 (dark) → 255 (bright)
    signalColor = `rgb(${red}, 0, 0)`;
    textColor = "white";
    signalMeaning = "OVERBOUGHT (Potential Sell Zone)";
  } else if (result.current_signal === "oversold") {
    // Green background: darker as %K approaches 0
    const intensity = Math.min(((20 - kValue) / 20) * 100, 100); // 0-100%
    const green = Math.round(100 + (intensity / 100) * 155); // 100 (dark) → 255 (bright)
    signalColor = `rgb(0, ${green}, 0)`;
    textColor = "white";
    signalMeaning = "OVERSOLD (Potential Buy Zone)";
  } else {
    // Neutral: Yellow text on white background
    signalColor = "white"; // White background for contrast
    textColor = "rgb(255, 215, 0)"; // Gold yellow text
    signalMeaning = "NEUTRAL (No Clear Signal)";
  }

  const analysisDate = formatDate(new Date(), locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const recentSignals = result.signal_changes.slice(-3);

  return `## 📊 Stochastic Oscillator - ${result.symbol}
*${analysisDate} • ${result.timeframe} timeframe*

### 📋 Key Metrics

<table style="width: 100%; border-collapse: collapse; border: 1px solid #d1d5db; margin-bottom: 1rem;">
  <tbody>
    <tr style="border-bottom: 1px solid #d1d5db;">
      <td style="padding: 0.5rem 1rem; font-weight: 600; border-right: 1px solid #d1d5db;">Signal</td>
      <td style="padding: 0.5rem 1rem; background-color: ${signalColor}; color: ${textColor}; font-weight: 700; border-right: 1px solid #d1d5db;">${signalMeaning}</td>
    </tr>
    <tr style="border-bottom: 1px solid #d1d5db;">
      <td style="padding: 0.5rem 1rem; border-right: 1px solid #d1d5db;">Current Price</td>
      <td style="padding: 0.5rem 1rem; border-right: 1px solid #d1d5db;">$${result.current_price.toFixed(2)}</td>
    </tr>
    <tr style="border-bottom: 1px solid #d1d5db;">
      <td style="padding: 0.5rem 1rem; border-right: 1px solid #d1d5db;">%K Line</td>
      <td style="padding: 0.5rem 1rem; border-right: 1px solid #d1d5db;">${result.current_k.toFixed(1)}%</td>
    </tr>
    <tr style="border-bottom: 1px solid #d1d5db;">
      <td style="padding: 0.5rem 1rem; border-right: 1px solid #d1d5db;">%D Line</td>
      <td style="padding: 0.5rem 1rem; border-right: 1px solid #d1d5db;">${result.current_d.toFixed(1)}%</td>
    </tr>
    <tr>
      <td style="padding: 0.5rem 1rem; border-right: 1px solid #d1d5db;">Parameters</td>
      <td style="padding: 0.5rem 1rem; border-right: 1px solid #d1d5db;">%K(${result.k_period}) %D(${result.d_period})</td>
    </tr>
  </tbody>
</table>

### 💡 Key Insights

${result.key_insights.map((insight) => `• ${insight}`).join("\n\n")}
${
  recentSignals.length > 0
    ? `

### 🔔 Recent Signals

${recentSignals
  .map((signal) => {
    const emoji =
      signal.type.toLowerCase() === "buy"
        ? "🟢"
        : signal.type.toLowerCase() === "sell"
          ? "🔴"
          : "🟡";
    return `${emoji} **${signal.type.toUpperCase()}**: ${signal.description}`;
  })
  .join("\n\n")}`
    : ""
}
`;
}

export function formatCompanyOverviewResponse(
  result: CompanyOverviewResponse,
): string {
  // Use backend-generated markdown if available
  if (result.formatted_markdown) {
    return result.formatted_markdown;
  }

  // Fallback to frontend formatting for backward compatibility
  return `## 🏢 Company Overview - ${result.symbol}
*${result.company_name}*

### 📋 Company Info

**Industry**: ${result.industry} | **Sector**: ${result.sector}
**Exchange**: ${result.exchange} | **Country**: ${result.country}

**Description**: ${result.description}

### 📊 Key Metrics

| Metric | Value | Metric | Value |
|--------|-------|--------|-------|
${result.market_cap ? `| Market Cap | $${(result.market_cap / 1e9).toFixed(2)}B |` : ""}${result.pe_ratio ? ` P/E Ratio | ${result.pe_ratio.toFixed(2)} |` : " - | - |"}
${result.eps ? `| EPS | $${result.eps.toFixed(2)} |` : ""}${result.profit_margin ? ` Profit Margin | ${result.profit_margin.toFixed(2)}% |` : " - | - |"}
${result.revenue_ttm ? `| Revenue (TTM) | $${(result.revenue_ttm / 1e9).toFixed(2)}B |` : ""}${result.dividend_yield ? ` Dividend Yield | ${result.dividend_yield.toFixed(2)}% |` : " - | - |"}
${result.beta ? `| Beta | ${result.beta.toFixed(2)} |` : ""}${result.percent_insiders ? ` % Insiders | ${result.percent_insiders.toFixed(2)}% |` : " - | - |"}
${result.percent_institutions ? `| % Institutions | ${result.percent_institutions.toFixed(2)}% |` : ""}${result.week_52_high ? ` 52W High | $${result.week_52_high.toFixed(2)} |` : " - | - |"}
${result.week_52_low ? `| 52W Low | $${result.week_52_low.toFixed(2)} |` : ""}
`;
}

export function formatCashFlowResponse(
  result: CashFlowResponse,
): string {
  // Use backend-generated markdown if available
  if (result.formatted_markdown) {
    return result.formatted_markdown;
  }

  // Fallback to frontend formatting for backward compatibility
  return `## 💵 Cash Flow - ${result.symbol}
*${result.company_name} • ${result.fiscal_date_ending}*

### 📋 Key Metrics

| Metric | Value |
|--------|-------|
${result.operating_cashflow ? `| Operating Cash Flow | $${(result.operating_cashflow / 1e6).toFixed(2)}M |` : ""}
${result.capital_expenditures ? `| Capital Expenditures | $${(Math.abs(result.capital_expenditures) / 1e6).toFixed(2)}M |` : ""}
${result.free_cashflow ? `| Free Cash Flow | $${(result.free_cashflow / 1e6).toFixed(2)}M |` : ""}
${result.dividend_payout ? `| Dividend Payout | $${(result.dividend_payout / 1e6).toFixed(2)}M |` : ""}

### 📝 Summary

${result.cashflow_summary}
`;
}

export function formatBalanceSheetResponse(
  result: BalanceSheetResponse,
): string {
  // Use backend-generated markdown if available
  if (result.formatted_markdown) {
    return result.formatted_markdown;
  }

  // Fallback to frontend formatting for backward compatibility
  return `## 📊 Balance Sheet - ${result.symbol}
*${result.company_name} • ${result.fiscal_date_ending}*

### 📋 Key Metrics

| Metric | Value |
|--------|-------|
${result.total_assets ? `| Total Assets | $${(result.total_assets / 1e6).toFixed(2)}M |` : ""}
${result.total_liabilities ? `| Total Liabilities | $${(result.total_liabilities / 1e6).toFixed(2)}M |` : ""}
${result.total_shareholder_equity ? `| Shareholder Equity | $${(result.total_shareholder_equity / 1e6).toFixed(2)}M |` : ""}
${result.current_assets ? `| Current Assets | $${(result.current_assets / 1e6).toFixed(2)}M |` : ""}
${result.current_liabilities ? `| Current Liabilities | $${(result.current_liabilities / 1e6).toFixed(2)}M |` : ""}
${result.cash_and_equivalents ? `| Cash & Equivalents | $${(result.cash_and_equivalents / 1e6).toFixed(2)}M |` : ""}

### 📝 Summary

${result.balance_sheet_summary}
`;
}

export function formatNewsSentimentResponse(
  result: NewsSentimentResponse,
): string {
  // Use backend-generated markdown if available
  if (result.formatted_markdown) {
    return result.formatted_markdown;
  }

  // Fallback to frontend formatting for backward compatibility
  return `## 📰 News Sentiment - ${result.symbol}

### 📝 Overall Sentiment

${result.overall_sentiment}

${
  result.positive_news.length > 0
    ? `### ✅ Positive News (${result.positive_news.length})

${result.positive_news
  .map(
    (article) =>
      `**${article.title}**
*${article.source} • Sentiment: ${article.sentiment_label} (${article.sentiment_score.toFixed(2)})*
[Read more](${article.url})`,
  )
  .join("\n\n")}`
    : ""
}

${
  result.negative_news.length > 0
    ? `### ❌ Negative News (${result.negative_news.length})

${result.negative_news
  .map(
    (article) =>
      `**${article.title}**
*${article.source} • Sentiment: ${article.sentiment_label} (${article.sentiment_score.toFixed(2)})*
[Read more](${article.url})`,
  )
  .join("\n\n")}`
    : ""
}
`;
}

export function formatMarketMoversResponse(
  result: MarketMoversResponse,
  locale: string,
): string {
  // Use backend-generated markdown if available
  if (result.formatted_markdown) {
    return result.formatted_markdown;
  }

  // Fallback to frontend formatting for backward compatibility
  return `## 📊 Market Movers
*Last Updated: ${formatTimestamp(result.last_updated, locale)}*

### 📈 Top Gainers

| Ticker | Price | Change | Volume |
|--------|-------|--------|--------|
${result.top_gainers
  .map(
    (mover) =>
      `| ${mover.ticker} | $${mover.price.toFixed(2)} | ${mover.change_percentage} | ${(mover.volume / 1e6).toFixed(2)}M |`,
  )
  .join("\n")}

### 📉 Top Losers

| Ticker | Price | Change | Volume |
|--------|-------|--------|--------|
${result.top_losers
  .map(
    (mover) =>
      `| ${mover.ticker} | $${mover.price.toFixed(2)} | ${mover.change_percentage} | ${(mover.volume / 1e6).toFixed(2)}M |`,
  )
  .join("\n")}

### 🔥 Most Active

| Ticker | Price | Change | Volume |
|--------|-------|--------|--------|
${result.most_active
  .map(
    (mover) =>
      `| ${mover.ticker} | $${mover.price.toFixed(2)} | ${mover.change_percentage} | ${(mover.volume / 1e6).toFixed(2)}M |`,
  )
  .join("\n")}
`;
}
