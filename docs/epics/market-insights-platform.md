# Epic: Market Insights Platform

> **Epic Type**: Brownfield Enhancement
> **Created**: 2025-12-20
> **Updated**: 2025-01-10
> **Status**: ✅ Complete
> **Estimated Stories**: 13 | **Completed**: 13

---

## Epic Goal

Create an extensible **Market Insights Platform** - a dedicated page (`/insights`) for visualizing customized financial metrics across multiple categories. The platform emphasizes **explainability** for both human users and AI agents, with a pluggable architecture that starts with "AI Sector Risk" and can expand to additional categories (Sector Rotation, Macro Environment, Market Breadth, etc.).

---

## Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Explainability First** | Every metric has plain-language explanation, methodology, and historical context |
| **Category Extensibility** | New metric categories can be added without changing core architecture |
| **AI-Native** | Every visualization is "talkable" - LLM can interpret and explain to users |
| **Performance** | Aggressive caching with incremental updates; <3s initial load |
| **Clear Labeling** | Category hierarchy and metric names are self-documenting |

---

## Existing System Context

| Aspect | Current State |
|--------|---------------|
| **Frontend Charting** | `lightweight-charts` v4.1.3 (TradingView) |
| **Backend Services** | `src/services/market_data/` with macro endpoints |
| **Alpha Vantage** | Premium key (75 calls/min), existing service abstraction |
| **Caching** | Redis with TTL strategies in `cache_utils.py` |
| **Agent Tools** | LangChain tools in `agent/tools/alpha_vantage/` |
| **Pages** | React Router at `src/pages/` |

---

## Architecture Overview

### Page Structure

```
/insights
│
├── [Header: "Market Insights" + Last Updated + Refresh Button]
│
├── [Category Tabs]
│   ├── 🎯 AI Sector Risk (v1 - This Epic)
│   ├── 🏭 Sector Rotation (Future)
│   ├── 🌍 Macro Environment (Future)
│   └── 📈 Market Breadth (Future)
│
├── [Composite Score Card]
│   └── Large gauge with weighted score + interpretation
│
├── [Metrics Grid]
│   └── 2x3 grid of individual metric cards
│
└── [Footer: Data Sources + Methodology Link]
```

### Metric Card Design (Explanation-First)

```
┌─────────────────────────────────────────────────────────────────┐
│  📊 AI Price Anomaly                              Score: 85/100 │
│  ───────────────────────────────────────────────────────────────│
│                                                                 │
│  [════════════════════════════════●══════]                      │
│  0          25          50         75        100                │
│  ▲ Accumulation    ▲ Normal    ▲ Caution   ▲ Euphoria          │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ 💡 WHAT THIS MEANS                                        │ │
│  │                                                           │ │
│  │ AI stocks (NVDA, MSFT, AMD, PLTR) are trading 2.3        │ │
│  │ standard deviations above their 200-day moving average.  │ │
│  │ This level of extension historically precedes            │ │
│  │ corrections 70% of the time within 30 days.              │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  [📖 Methodology]  [📈 History]  [🤖 Ask AI About This]        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Data Model

```typescript
// Category Definition
interface InsightCategory {
  id: string;                    // "ai_sector_risk"
  name: string;                  // "AI Sector Risk"
  icon: string;                  // "🎯"
  description: string;           // "Measures bubble risk..."
  metrics: InsightMetric[];
  compositeWeights: Record<string, number>;
}

// Individual Metric
interface InsightMetric {
  id: string;                    // "ai_price_anomaly"
  name: string;                  // "AI Price Anomaly"
  score: number;                 // 0-100
  status: "low" | "normal" | "elevated" | "high";
  explanation: MetricExplanation;
  dataSources: string[];         // ["TIME_SERIES_DAILY"]
  lastUpdated: string;           // ISO 8601
}

// Explanation (Core UX Feature)
interface MetricExplanation {
  summary: string;               // One-liner for quick scan
  detail: string;                // 2-3 sentences with specifics
  methodology: string;           // How it's calculated
  formula?: string;              // Optional math formula
  historicalContext: string;     // "Last time this high..."
  actionableInsight: string;     // "Consider..."
  thresholds: {                  // For visualization
    low: number;                 // 0-25
    normal: number;              // 25-50
    elevated: number;            // 50-75
    high: number;                // 75-100
  };
}
```

### API Structure

```
/api/insights
│
├── GET /categories
│   └── Returns: List of available categories with metadata
│
├── GET /{category_id}
│   └── Returns: All metrics for category + composite score
│
├── GET /{category_id}/{metric_id}
│   └── Returns: Single metric with full explanation
│
├── GET /{category_id}/composite
│   └── Returns: Weighted composite with breakdown
│
└── POST /{category_id}/refresh
    └── Forces cache invalidation and recalculation
```

---

## First Category: AI Sector Risk

### Metrics Definition

| # | Metric ID | Name | Data Source | Calculation | Weight |
|---|-----------|------|-------------|-------------|--------|
| 1 | `ai_price_anomaly` | AI Price Anomaly | TIME_SERIES_DAILY | Z-score of NVDA,MSFT,AMD,PLTR vs 200 SMA | 20% |
| 2 | `news_sentiment` | News Sentiment | NEWS_SENTIMENT | Normalized avg sentiment (-0.35 to +0.35 → 0-100) | 20% |
| 3 | `smart_money_flow` | Smart Money Flow | TIME_SERIES_INTRADAY | First hour vs last hour volume divergence | 20% |
| 4 | `ipo_heat` | IPO Heat | IPO_CALENDAR | Count of IPOs in next 90 days | 10% |
| 5 | `market_liquidity` | Market Liquidity | FRED API | RRP balance + SOFR-EFFR spread (actual liquidity) | 13% |
| 6 | `fed_expectations` | Fed Expectations | TREASURY_YIELD | 2Y yield slope over 20 days | 12% |
| 7 | `options_put_call_ratio` | Put/Call Ratio | HISTORICAL_OPTIONS | Aggregate PCR across AI basket (Premium) | 15% |

### Interpretation Zones

| Score Range | Status | Color | Meaning |
|-------------|--------|-------|---------|
| 0-25 | Low | 🟢 Green | Fear / Accumulation Zone |
| 25-50 | Normal | 🔵 Blue | Normal Bull Market |
| 50-75 | Elevated | 🟡 Yellow | Caution / Late Cycle |
| 75-100 | High | 🔴 Red | Euphoria / Bubble Risk |

---

## Stories

### Story 1: Backend - Insights Service Architecture

**Goal**: Create extensible service layer for insights platform

**Deliverables**:
- `src/services/insights/` module structure:
  ```
  insights/
  ├── __init__.py
  ├── base.py              # Abstract InsightCategory class
  ├── models.py            # Pydantic models for metrics/explanations
  ├── registry.py          # Category registry (plugin system)
  └── categories/
      └── ai_sector_risk.py  # First category implementation
  ```
- Category registry pattern for adding new categories
- Explanation generation for each metric
- Redis caching with category-level TTL

**Acceptance Criteria**:
- [x] Abstract base class defines metric interface
- [x] New categories can be added by creating single file
- [x] All metrics return full explanation objects
- [x] Registry auto-discovers categories on startup

**Implementation**: Story 2.1 ✅

---

### Story 2: Backend - AI Sector Risk Implementation

**Goal**: Implement all 7 metrics for the first category

**Deliverables**:
- Add missing Alpha Vantage endpoints:
  - `TREASURY_YIELD` (10Y, 2Y) in `market_data/macro.py`
  - `IPO_CALENDAR` (CSV parsing) in `market_data/macro.py`
  - `HISTORICAL_OPTIONS` in `market_data/options.py` (v0.9.0)
- Add FRED API integration:
  - `FREDService` for SOFR, EFFR, RRP Balance data (v0.9.0)
- Implement calculation logic:
  - Z-score calculation with 200 SMA
  - Sentiment normalization
  - Intraday volume divergence detection
  - IPO count with date filtering
  - Yield spread and slope calculations
  - Options Put/Call Ratio (v0.9.0)
  - Market Liquidity from FRED (v0.9.0)
- Explanation templates for each metric
- Rate limiter integration (queue for free tier)

**Acceptance Criteria**:
- [x] All 7 metrics return valid 0-100 scores (v0.9.0)
- [x] Each metric has complete explanation object
- [x] Rate limiting prevents API quota exhaustion
- [x] Graceful degradation on partial API failure

**Implementation**: Stories 2.1, 2.2, 2.6, 2.7, 2.8 ✅

---

### Story 3: Backend - Insights API Endpoints

**Goal**: Create REST API for frontend consumption

**Deliverables**:
- `src/api/insights.py` router:
  - `GET /api/insights/categories`
  - `GET /api/insights/{category_id}`
  - `GET /api/insights/{category_id}/{metric_id}`
  - `GET /api/insights/{category_id}/composite`
  - `POST /api/insights/{category_id}/refresh`
- Response models with full explanation schemas
- OpenAPI documentation with examples
- Error responses with helpful messages

**Acceptance Criteria**:
- [x] All endpoints return proper JSON with explanations
- [x] Swagger docs show example responses
- [x] 404 for invalid category/metric IDs
- [x] Refresh endpoint invalidates cache correctly

**Implementation**: Story 2.1, 2.3 ✅

---

### Story 4: Frontend - Insights Page & Category System

**Goal**: Create the `/insights` page with category navigation

**Deliverables**:
- `src/pages/InsightsPage.tsx` - Main page component
- `src/components/insights/` module:
  ```
  insights/
  ├── CategoryTabs.tsx        # Tab navigation
  ├── CompositeScoreCard.tsx  # Large central gauge
  ├── MetricsGrid.tsx         # 2x3 grid layout
  ├── MetricCard.tsx          # Individual metric with explanation
  ├── ScoreGauge.tsx          # SVG arc gauge component
  ├── ExplanationPanel.tsx    # Expandable explanation section
  └── MethodologyModal.tsx    # Full methodology popup
  ```
- Route configuration in `App.tsx`
- Navigation link in header/sidebar
- Responsive layout (mobile: stack, desktop: grid)

**Acceptance Criteria**:
- [x] Page loads at `/insights` route
- [x] Category tabs switch content
- [x] All 7 metrics display with gauges (v0.9.0)
- [x] Explanations visible by default (not hidden)
- [x] Mobile responsive layout works

**Implementation**: Story 2.4 ✅

---

### Story 5: Frontend - Explanation UX & Interactivity

**Goal**: Rich explanation experience with AI integration

**Deliverables**:
- Explanation panel with sections:
  - Summary (always visible)
  - Methodology (expandable)
  - Historical context (expandable)
  - Actionable insight (highlighted)
- "Ask AI About This" button:
  - Opens chat panel with pre-loaded context
  - Message template: "Explain the {metric_name} indicator showing {score}"
- History sparkline (last 30 days trend)
- Threshold markers on gauge
- Loading/skeleton states
- Error states with retry

**Acceptance Criteria**:
- [x] All explanation sections render correctly
- [x] "Ask AI" opens chat with correct context
- [x] Sparkline shows 30-day history
- [x] Threshold zones visually distinguished
- [x] Loading states don't flash

**Implementation**: Stories 2.4, 2.5 ✅

---

### Story 6: LLM Integration - Talkable Insights

**Goal**: Enable LLM to interpret and discuss any insight metric

**Deliverables**:
- `src/agent/tools/insights_tools.py`:
  - `get_market_insights` - Overview of all categories
  - `get_category_insights` - All metrics for a category
  - `explain_insight_metric` - Deep dive on specific metric
  - `compare_insight_history` - Trend analysis
- Response formatters with rich markdown:
  - Score + status emoji
  - Explanation in conversational tone
  - Historical comparison
  - Actionable recommendations
- Tool registration in ReAct agent
- Example prompts for CLAUDE.md

**Acceptance Criteria**:
- [x] "What's the AI bubble risk?" returns formatted insights
- [x] "Explain the yield curve indicator" gives methodology
- [x] "How has sentiment changed this week?" gives trend
- [x] Tool responses cached appropriately

**Implementation**: Story 2.5 ✅

---

## Phase 2: Trend Visualization & Data Management Layer

> **Added**: 2025-12-27
> **Reference**: [Sprint Change Proposal](../stories/sprint-change-proposal-ai-sector-risk-trends.md)

These stories enhance the insights platform with historical trend visualization, performance optimization, and a unified Data Manager Layer (DML) as the single source of truth for all data access.

---

### Story 7: Data Manager Layer (DML) - Foundation 🏗️

**Goal**: Create single source of truth for ALL data access across the application

**Deliverables**:
```
backend/src/services/data_manager/
├── __init__.py
├── manager.py          # DataManager class
├── cache.py            # Redis operations
├── keys.py             # Naming conventions (market:{granularity}:{symbol})
└── types.py            # OHLCVData, TrendPoint, etc.
```

**Key Features**:
- Unified data access interface for all consumers (Charts, AI Tools, Insights, Analysis)
- Consistent cache key naming convention: `{domain}:{granularity}:{symbol}`
- Tiered caching: Hot (Redis) → Warm (MongoDB)
- No caching for intraday (1min-15min), cache for daily+ granularity
- Pre-fetch shared data pattern to eliminate duplicate API calls

**Acceptance Criteria**:
- [x] `DataManager.get_ohlcv()` returns cached data for daily+ granularity
- [x] `DataManager.get_ohlcv()` returns fresh data for intraday (no cache)
- [x] Key convention: `market:{granularity}:{symbol}` consistently applied
- [x] Existing AI tools migrated to use DML
- [x] Existing chart APIs migrated to use DML
- [x] `AlphaVantageMarketDataService` marked deprecated
- [x] No direct Alpha Vantage calls outside DML
- [x] Treasury 2Y data used by fed_expectations metric
- [x] FRED data (RRP, SOFR, EFFR) used by market_liquidity metric

**Implementation**: Story 2.1 ✅

**Verification**:
```bash
# Cache hit test
redis-cli GET "market:daily:AAPL" | jq 'length'

# No bypass check
grep -r "AlphaVantageMarketDataService" backend/src/ | grep -v "deprecated"
# Expected: 0 matches
```

---

### Story 8: Daily Snapshot Cron Job ⏰

**Goal**: Automated daily data collection with optimized parallel performance

**Deliverables**:
- K8s CronJob manifest: `.pipeline/k8s/base/insights-cron.yaml`
- Parallel calculation with `asyncio.gather()` for all 7 metrics
- Pre-fetch shared data pattern (fetch once, use many)
- MongoDB snapshot persistence to `insight_snapshots` collection
- Redis cache update with 24-hour TTL

**Performance Architecture**:
```
PHASE 1: Pre-fetch all shared data (parallel)
├── Daily bars (AI symbols)
├── Intraday bars (top 3 AI symbols)
├── Treasury 10Y
├── Treasury 2Y          ← Used by fed_expectations
├── FRED Data (RRP, SOFR, EFFR) ← Used by market_liquidity
├── News sentiment
└── IPO calendar

PHASE 2: Calculate metrics (parallel with shared data)
├── ai_price_anomaly(shared_data)
├── news_sentiment(shared_data)
├── smart_money_flow(shared_data)
├── ipo_heat(shared_data)
├── market_liquidity(fred_data)   ← Uses FRED RRP, SOFR, EFFR
└── fed_expectations(shared_data) ← Uses shared Treasury 2Y

PHASE 3: Batch persist
├── MongoDB: insight_snapshots
└── Redis: insights:ai_sector_risk:latest (24hr TTL)
```

**Acceptance Criteria**:
- [x] Cron runs daily at 9:30 AM ET (14:30 UTC)
- [x] All 7 metrics calculated in parallel (< 10 seconds total vs 30+ sequential)
- [x] Treasury 2Y fetched ONCE (used by fed_expectations)
- [x] FRED data fetched ONCE (used by market_liquidity)
- [x] Snapshot saved to `insight_snapshots` collection with date index
- [x] Redis key `insights:ai_sector_risk:latest` updated with 24hr TTL
- [x] Graceful handling of partial API failures (return_exceptions=True)

**Implementation**: Story 2.2 ✅

**Verification**:
```bash
# Manual trigger
kubectl create job insights-manual --from=cronjob/insights-cron

# Check MongoDB
mongosh --eval "db.insight_snapshots.findOne({date: ISODate('2025-12-27')})"

# Check Redis
redis-cli GET "insights:ai_sector_risk:latest" | jq .composite_score

# Data consistency check
REDIS=$(redis-cli GET "insights:ai_sector_risk:latest" | jq .composite_score)
MONGO=$(mongosh --eval "db.insight_snapshots.find().sort({date:-1}).limit(1)" | jq .composite_score)
[ "$REDIS" == "$MONGO" ] && echo "✅ Consistent" || echo "❌ Mismatch"
```

---

### Story 9: Trend API Endpoints 📈

**Goal**: API endpoints for historical trend data queries

**Deliverables**:
- New endpoint: `GET /api/insights/{category_id}/trend`
- Query parameters: `?days=30` (default), supports 7, 14, 30, 60, 90
- `TrendDataPoint` response model in `insights_models.py`
- MongoDB date range query optimization

**API Response Schema**:
```json
{
  "category_id": "ai_sector_risk",
  "days": 30,
  "trend": [
    {"date": "2025-12-27", "composite_score": 72.5, "status": "elevated"},
    {"date": "2025-12-26", "composite_score": 70.2, "status": "elevated"}
  ],
  "metrics": {
    "ai_price_anomaly": [
      {"date": "2025-12-27", "score": 85, "status": "high"},
      {"date": "2025-12-26", "score": 82, "status": "high"}
    ],
    "news_sentiment": [...],
    "smart_money_flow": [...],
    "ipo_heat": [...],
    "market_liquidity": [...],
    "fed_expectations": [...]
  }
}
```

**Acceptance Criteria**:
- [x] Endpoint returns 30 days by default
- [x] Supports `?days=7|14|30|60|90` query parameter
- [x] Each datapoint includes date, score, status
- [x] Includes both composite and individual metric trends
- [x] Returns empty array gracefully if < requested days of data
- [x] Response time < 500ms for 30-day query

**Implementation**: Story 2.3 ✅

---

### Story 10: Frontend Trend Visualization 📊

**Goal**: Interactive trend display with swipe gesture and scale controls

**Deliverables**:
```
frontend/src/components/insights/
├── TrendSparkline.tsx      # Compact sparkline for metric cards
├── TrendChart.tsx          # Full trend chart with zoom/pan
├── SwipeContainer.tsx      # Swipe left gesture handler
└── hooks/useInsightTrend.ts # Data fetching hook
```

**UX Requirements**:
- **Default**: 30 days displayed in sparkline
- **Swipe left**: Load more history (60, 90 days)
- **Scale/zoom**: Pinch gesture to show more/fewer datapoints
- **Today highlight**: Current day's datapoint in different color/marker
- **Responsive**: Works on mobile and desktop

**Updated Metric Card Design**:
```
┌─────────────────────────────────────────────────────────────────┐
│  📊 AI Price Anomaly                              Score: 85/100 │
│  ───────────────────────────────────────────────────────────────│
│                                                                 │
│  [30-Day Trend Sparkline ~~~~~~~~~~~●]  ← Today highlighted    │
│                              ← Swipe left for more history     │
│                                                                 │
│  [════════════════════════════════●══════]                      │
│  0          25          50         75        100                │
│                                                                 │
│  💡 AI stocks trading 2.3 std dev above 200-day SMA...         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Acceptance Criteria**:
- [x] Sparkline shows 30-day trend in each metric card
- [x] Today's datapoint highlighted with distinct color/marker
- [x] Swipe left gesture loads more history (60, 90 days)
- [x] Pinch/zoom scales chart to show more/fewer datapoints
- [x] Loading skeleton while fetching trend data
- [x] Mobile responsive layout

**Implementation**: Story 2.4 ✅

---

### Story 11: AI Tools Redis Integration 🤖

**Goal**: Fast AI tool access via DML cache with trend query capability

**Deliverables**:
- Update `insights_tools.py` to use DataManager
- New tool: `get_insight_trend` for historical queries
- Response time < 100ms for cached data

**New Tool**:
```python
@tool
async def get_insight_trend(category_id: str, days: int = 30) -> str:
    """
    Get historical trend for a market insight category.

    Shows how the composite score and individual metrics
    have changed over the specified number of days.

    Args:
        category_id: Category identifier (e.g., "ai_sector_risk")
        days: Number of days of history (default: 30, max: 90)

    Returns:
        Trend analysis with score changes and patterns

    Example:
        get_insight_trend("ai_sector_risk", 30)
    """
```

**Acceptance Criteria**:
- [x] `get_insight_category()` reads from Redis via DML (no API calls)
- [x] `get_insight_trend()` returns formatted 30-day history
- [x] Tool response time < 100ms when data is cached
- [x] Graceful fallback if cache miss (trigger calculation or return stale)
- [x] Rich markdown formatting with trend direction indicators (↑↓→)

**Implementation**: Story 2.5 ✅

**Verification**:
```bash
# Performance test
time curl -X POST /api/chat -d '{"message": "What is the AI sector risk?"}'
# Expected: < 2 seconds (vs 15-30 seconds without cache)

# Trend query test
curl -X POST /api/chat -d '{"message": "How has AI sector risk changed this month?"}'
# Expected: Returns 30-day trend analysis
```

---

### Story 12: Put/Call Ratio Metric (Options Sentiment) 📊

> **Added**: 2025-12-30
> **Reference**: [Story 2.6](../stories/2.6.story.md)

**Goal**: Add 7th metric to AI Sector Risk using Alpha Vantage Premium Options API

**Deliverables**:
- `get_historical_options()` method in Alpha Vantage service
- `_calculate_options_put_call_ratio()` in AISectorRiskCategory
- Weight rebalancing for 7-metric composite score
- Graceful degradation for non-Premium API keys

**Financial Rationale**:
- Put/Call Ratio (PCR) is a **contrarian sentiment indicator**
- Low PCR (< 0.5) = extreme bullishness = bubble risk
- High PCR (> 1.0) = fear/hedging = potential bottom
- Complements existing metrics with options market sentiment

**Acceptance Criteria**:
- [x] `options_put_call_ratio` metric added as 7th indicator
- [x] Uses Alpha Vantage HISTORICAL_OPTIONS (Premium) endpoint
- [x] Calculates aggregate PCR across top 5 AI basket symbols
- [x] Score inverted: Low PCR → High Risk Score (contrarian)
- [x] Graceful placeholder if Premium API unavailable
- [x] Weights rebalanced to 100% across 7 metrics
- [x] Unit tests with mocked API responses

**Implementation**: Stories 2.6, 2.8 ✅

**Verification**:
```bash
# Check metric in API response
curl -s http://localhost:3000/api/insights/ai_sector_risk | jq '.metrics[] | select(.id == "options_put_call_ratio")'

# Verify 7 metrics returned
curl -s http://localhost:3000/api/insights/ai_sector_risk | jq '.metrics | length'
# Expected: 7
```

---

### Story 13: Replace Yield Curve with Market Liquidity 💧

> **Added**: 2025-12-30
> **Reference**: [Story 2.7](../stories/2.7.story.md)

**Goal**: Replace `yield_curve` (10Y-2Y spread) with true `market_liquidity` metric using FRED API

**Rationale**:
- `yield_curve` measures term structure/economic expectations, NOT actual liquidity
- Professional liquidity assessment uses: RRP balance, SOFR-EFFR spread
- Core theory: "当资金充裕 → 容易出现泡沫; 当资金不充裕 → 不容易出现泡沫"

**Data Sources (FRED API)**:
| Series | Data | Purpose |
|--------|------|---------|
| `RRPONTSYD` | Fed Reverse Repo Balance | System liquidity level |
| `SOFR` | Secured Overnight Financing Rate | Overnight funding cost |
| `EFFR` | Effective Federal Funds Rate | Overnight funding benchmark |

**Calculation**:
```
market_liquidity = (
    RRP_Balance_Score × 0.50 +      # High RRP = abundant liquidity = bubble fuel
    SOFR_EFFR_Spread_Score × 0.30 + # Low spread = no stress = bubble can form
    RRP_20d_Trend_Score × 0.20      # Rising RRP = increasing liquidity
)
```

**Acceptance Criteria**:
- [x] FRED API service integrated (`backend/src/services/market_data/fred.py`)
- [x] `yield_curve` metric removed from AI Sector Risk
- [x] `market_liquidity` metric added with 13% weight
- [x] High liquidity → High risk score (bubble CAN form)
- [x] FRED API key added to K8s secrets
- [x] Graceful fallback if FRED unavailable
- [x] Unit tests with mocked FRED responses

**Implementation**: Story 2.7 ✅

**Verification**:
```bash
# Check new metric
curl -s http://localhost:3000/api/insights/ai_sector_risk | jq '.metrics[] | select(.id == "market_liquidity")'

# Verify yield_curve removed
curl -s http://localhost:3000/api/insights/ai_sector_risk | jq '.metrics[] | select(.id == "yield_curve")'
# Expected: null/empty
```

---

## Future Categories (Backlog)

These categories can be added by implementing the `InsightCategory` base class:

| Category | Metrics (Examples) | Priority |
|----------|-------------------|----------|
| **Sector Rotation** | Tech/Value ratio, Cyclical/Defensive, Growth/Value | Medium |
| **Macro Environment** | Inflation trend, GDP growth, Dollar index | Medium |
| **Market Breadth** | Advance/Decline, New Highs/Lows, McClellan | Low |
| **Volatility Regime** | VIX term structure, SKEW index | Low |
| **Credit Conditions** | HY spreads, TED spread, Bank lending | Low |

---

## Technical Architecture

### Caching Strategy

> **Updated 2025-12-27**: All caching now managed through Data Manager Layer (DML)

```
┌─────────────────────────────────────────────────────────────┐
│                DATA MANAGER LAYER (DML)                      │
│              *** SINGLE SOURCE OF TRUTH ***                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Cache Key Convention: {domain}:{granularity}:{symbol}      │
│  ├── market:daily:AAPL           (OHLCV bars)               │
│  ├── macro:treasury:2y           (Treasury yields)          │
│  ├── sentiment:news:technology   (News sentiment)           │
│  ├── etf:holdings:AIQ            (ETF basket)               │
│  └── insights:ai_sector_risk:latest  (Computed results)     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 1: Raw API Data (via DML)                            │
│  ├── Intraday (1min-15min): NO CACHE (always fresh)         │
│  ├── Daily+ OHLCV: 1-4 hour TTL                             │
│  ├── News sentiment: 1 hour TTL                             │
│  ├── IPO calendar: 24 hour TTL                              │
│  ├── Treasury yields: 1 hour TTL                            │
│  └── ETF holdings: 24 hour TTL                              │
│                                                             │
│  Layer 2: Computed Insights (Redis)                         │
│  ├── insights:{category}:latest: 24 hour TTL                │
│  └── Updated daily by cron job                              │
│                                                             │
│  Layer 3: Historical Snapshots (MongoDB)                    │
│  ├── Collection: insight_snapshots                          │
│  ├── Retention: 90 days                                     │
│  └── Used for trend queries                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**DML Guarantees**:
- All data consumers use same cache (no duplication)
- Consistent key naming across application
- Shared data fetched once (e.g., Treasury 2Y for 2 metrics)
- No direct API calls outside DML

### Database Schema

> **Updated 2025-12-27**: Added composite_status field for trend queries

```javascript
// Collection: insight_snapshots
{
  "_id": ObjectId,
  "category_id": "ai_sector_risk",
  "date": ISODate("2025-12-27"),
  "composite_score": 72.5,
  "composite_status": "elevated",           // Added for trend display
  "metrics": {
    "ai_price_anomaly": { "score": 85, "status": "high" },
    "news_sentiment": { "score": 78, "status": "elevated" },
    "smart_money_flow": { "score": 52, "status": "normal" },
    "ipo_heat": { "score": 35, "status": "normal" },
    "market_liquidity": { "score": 45, "status": "normal" },
    "fed_expectations": { "score": 62, "status": "elevated" }
  },
  "created_at": ISODate
}

// Index for efficient trend queries
db.insight_snapshots.createIndex({ "category_id": 1, "date": -1 })

// Retention: 90 days (managed by application or TTL index)
```

**See also**: [Database Schema Documentation](../architecture/database-schema.md) (needs update for this collection)

---

## Compatibility Requirements

- [x] Existing APIs remain unchanged
- [x] New MongoDB collection (additive)
- [x] UI follows existing TailwindCSS patterns
- [x] No changes to existing pages
- [x] Agent tools extend existing pattern

---

## Risk Mitigation

| Risk | Mitigation | Rollback |
|------|------------|----------|
| **API Rate Limits** | Queue with delay, aggressive caching | Use cached data only |
| **Calculation Errors** | Unit tests, validation | Show "unavailable" |
| **Complex UX** | User testing, iterative design | Simplify explanations |
| **Performance** | Lazy loading, skeleton states | Reduce metrics shown |

---

## Definition of Done

### Phase 1 (Stories 1-6)
- [x] All 6 stories completed with acceptance criteria
- [x] Insights page accessible at `/insights`
- [x] All 7 AI Risk metrics functional (v0.9.0)
- [x] Explanations clear and helpful
- [x] LLM can discuss any metric

### Phase 2 (Stories 7-13)
- [x] Data Manager Layer (DML) is single source of truth
- [x] All data consumers migrated to DML
- [x] Daily cron job populates snapshots
- [x] Trend API returns 30-day history
- [x] Frontend sparklines show trend with today highlighted
- [x] AI tools respond < 100ms from cache
- [x] Swipe gesture loads more history
- [x] Put/Call Ratio metric with reusable service
- [x] Market Liquidity metric via FRED API

### Overall
- [x] Documentation complete
- [x] No regression in existing features
- [x] Performance verified (< 10s cron, < 100ms cached reads)

---

## Technical References

| Reference | Location |
|-----------|----------|
| Alpha Vantage Service | `backend/src/services/market_data/` |
| Lightweight Charts | `frontend/src/components/chart/` |
| Agent Tools Pattern | `backend/src/agent/tools/alpha_vantage/` |
| Cache Utils | `backend/src/core/utils/cache_utils.py` |
| Page Components | `frontend/src/pages/` |
| API Router Pattern | `backend/src/api/` |
| **Data Manager Layer** | `backend/src/services/data_manager/` (Story 7) |
| **Insights Cron Job** | `.pipeline/k8s/base/insights-cron.yaml` (Story 8) |
| **Sprint Change Proposal** | `docs/stories/sprint-change-proposal-ai-sector-risk-trends.md` |

---

## Handoff to Story Manager

**Key considerations for story development:**

### Phase 1 (Stories 1-6) - Core Platform
1. This is an **extensible platform** - architecture must support future categories
2. **Explainability is core UX** - not an afterthought
3. **AI integration** - every metric must be "talkable"
4. Follow existing patterns in `market_data/` and `agent/tools/`
5. Each story should verify no regression in existing features

### Phase 2 (Stories 7-11) - Trend & DML Enhancement
1. **Story 7 (DML) is foundational** - must be completed first, all other Phase 2 stories depend on it
2. **DML is the single source of truth** - no bypass allowed, all consumers must migrate
3. **Performance is critical** - parallel execution, shared data, cache-first access
4. **Cron job runs at market open** - 9:30 AM ET (14:30 UTC)
5. **UX: Swipe + Scale** - mobile-first gesture interactions for trend exploration

### Story Dependencies
```
Story 7 (DML) ──┬──► Story 8 (Cron) ──┬──► Story 9 (Trend API) ──► Story 10 (Frontend)
                │                     │
                └──► Story 11 (AI Tools) ◄─┘
```

## Epic Summary

**✅ EPIC COMPLETE** (2025-01-10)

The epic delivered a **Market Insights Platform** with:
- AI Sector Risk category with 7 metrics (v0.9.0)
- 30-day trend visualization with swipe/scale UX
- Data Manager Layer for unified, high-performance data access
- AI tools with < 100ms response time from cache
- Put/Call Ratio with reusable service and AI tool (Story 2.8)
- Market Liquidity metric via FRED API (Story 2.7)

**Stories Completed**: 2.1 → 2.8 (all 8 stories)
**Production URL**: http://localhost:3000/insights
