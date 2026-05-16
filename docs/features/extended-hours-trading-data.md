---
title: Extended Hours Trading Data (Pre-Market & After-Hours)
status: shipped
version: backend@0.24.0, frontend@0.19.0
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/src/services/data_manager/types.py
  - backend/src/services/market_data/yfinance_bars.py
  - frontend/src/components/portfolio/PortfolioSummaryTable.tsx
---

# Feature: Extended Hours Trading Data (Pre-Market & After-Hours)

> Shipped in backend v0.24.0 / frontend v0.19.0. The original design document
> (`QuoteData.session` literal + SessionBadge UI) lived as a separate
> implementation plan during development; this spec is the canonical reference
> for the shipped behavior.

## Context

Active traders need access to pre-market and after-hours trading data to make informed decisions outside regular trading hours (9:30 AM - 4:00 PM ET). Currently, KlineMatrix only shows regular market hours data.

**User Story**:
As an active trader, I want to view pre-market and after-hours price movements, so that I can react to overnight news and earnings announcements before the market opens.

**Background**:
- Current implementation uses yfinance (Yahoo Finance), which only provides regular hours data
- Trading sessions:
  - **Pre-Market**: 4:00 AM - 9:30 AM ET
  - **Regular Hours**: 9:30 AM - 4:00 PM ET
  - **After-Hours**: 4:00 PM - 8:00 PM ET
- User feedback: "要不要考虑加入盘前/盘后的数据" (Should we add pre/post-market data?)

**Related Features**:
- Market Data API (`/api/market_data.py`)
- Chart Panel (`ChartPanel.tsx`)
- Ticker Data Service (`ticker_data_service.py`)

---

## Problem Statement

**Current Limitations**:
1. ❌ No visibility into pre-market price movements (earnings reports, news)
2. ❌ No after-hours data (earnings calls, analyst upgrades/downgrades)
3. ❌ Incomplete picture of stock volatility and momentum
4. ❌ Traders cannot identify gap-up/gap-down opportunities

**Impact**:
- Users miss critical trading signals from extended hours
- Cannot plan entry/exit strategies around pre-market moves
- Competitive disadvantage vs. platforms with extended hours data

---

## Proposed Solution

### High-Level Approach

Add extended hours trading data by integrating **Alpha Vantage API** as a secondary data source alongside yfinance. Provide session-based filtering in the UI to toggle between All/Pre-Market/Regular/After-Hours.

**Key Components**:
1. **Data Provider**: Alpha Vantage Intraday API (extended hours enabled)
2. **Backend Service**: New `ExtendedHoursDataService`
3. **API Endpoint**: `GET /api/market/price/{symbol}/extended`
4. **Session Splitter**: Classify data by time into 3 sessions
5. **Frontend UI**: Session toggle buttons above chart
6. **Chart Rendering**: Color-coded candlesticks by session

### Technical Architecture

```
User Browser
    ↓ (Request AAPL with extended hours)
Frontend ChartPanel.tsx
    ↓ (GET /api/market/price/AAPL/extended?interval=5min)
Backend Market Data API (/api/market_data.py)
    ↓ (Call ExtendedHoursDataService)
Extended Hours Service (/core/data/extended_hours_service.py)
    ↓ (Fetch from Alpha Vantage)
Alpha Vantage API (TIME_SERIES_INTRADAY + extended_hours=true)
    ↓ (Return raw data)
Session Splitter (_split_by_session)
    ↓ (Classify by time)
Response: { pre_market: [...], regular: [...], after_hours: [...] }
    ↓ (Render chart)
Frontend Chart (color-coded by session)
```

### Data Flow

1. **Fetch Phase**:
   - User searches for "AAPL" → Frontend requests extended hours data
   - Backend calls Alpha Vantage with `extended_hours=true`
   - Receives intraday data with timestamps

2. **Processing Phase**:
   - Backend splits data by session based on Eastern Time:
     - 04:00-09:30 → Pre-Market
     - 09:30-16:00 → Regular Hours
     - 16:00-20:00 → After-Hours
   - Returns structured JSON with 3 arrays

3. **Display Phase**:
   - Frontend shows session toggle buttons
   - User selects "All Sessions" → Display all data
   - Color-code candlesticks:
     - Pre-Market: Blue
     - Regular Hours: Green/Red (bull/bear)
     - After-Hours: Orange

---

## Implementation Plan

### Phase 1: Alpha Vantage Integration (Day 1-2)

**Service**: `ExtendedHoursDataService` with methods: `get_extended_hours_data()`, `_split_by_session()`, `_classify_session()`

**Config**: `ALPHA_VANTAGE_API_KEY`, `ENABLE_EXTENDED_HOURS`

**Pricing**: Free (25/day) or Premium ($50/mo, 75/min)

### Phase 2: Backend API Endpoint (Day 2-3)

**Endpoint**: `GET /api/market/price/{symbol}/extended?interval=5min`

**Response**: `{ symbol, interval, sessions: { pre_market: [], regular: [], after_hours: [] }, metadata }`

### Phase 3: Session Classification Logic (Day 3)

**Algorithm**: Convert timestamp to ET, classify by hour:
- 04:00-09:29 → pre_market
- 09:30-15:59 → regular
- 16:00-19:59 → after_hours
- else → closed

**Edge Cases**: DST transitions (use zoneinfo), weekends/holidays (future)

### Phase 4: Frontend Session Toggle (Day 4-5)

**Component** (`ChartPanel.tsx`): Session toggle buttons (All/Pre-Market/Regular/After-Hours)

**State**: `session: 'all' | 'pre' | 'regular' | 'after'`

**Data Filtering**: Filter `extendedData.sessions` based on selected session

### Phase 5: Chart Styling by Session (Day 5-6)

**Color Scheme**:
- Pre-Market: Blue (#3B82F6 up, #1E40AF down)
- Regular: Green/Red (#10B981 up, #EF4444 down)
- After-Hours: Orange (#F59E0B up, #D97706 down)

**Legend**: Color indicators for each session type

---

## Data Models

**Backend** (`ExtendedHoursDataResponse`): `symbol`, `interval`, `sessions: dict[str, list[PricePoint]]`, `metadata`

**PricePoint**: `time` (ISO 8601), `open`, `high`, `low`, `close`, `volume`, `session` ("pre_market" | "regular" | "after_hours")

**Frontend** (`ExtendedHoursData`): Same structure with TypeScript types. Sessions contain arrays of PricePoint objects.

---

## API Endpoints

### Get Extended Hours Data (NEW)

**Endpoint**: `GET /api/market/price/{symbol}/extended?interval=5min`

**Response**: `{ symbol, interval, sessions: { pre_market: [], regular: [], after_hours: [] }, metadata: { timezone, last_refreshed } }`

**Status Codes**: 200 (Success), 400 (Invalid input), 429 (Rate limit), 500 (API error)

### Regular Data Endpoint (Unchanged)

`GET /api/market/price/{symbol}?interval=1d&period=6mo` - Keeps existing behavior (yfinance, regular hours only)

---

## Trading Hours Reference

### US Stock Market Sessions (Eastern Time)

| Session | Start | End | Duration | Description |
|---------|-------|-----|----------|-------------|
| Pre-Market | 4:00 AM | 9:30 AM | 5.5 hours | Early trading, lower volume |
| Regular Hours | 9:30 AM | 4:00 PM | 6.5 hours | Main trading session |
| After-Hours | 4:00 PM | 8:00 PM | 4 hours | Post-close trading, earnings reactions |

**Key Characteristics**:
- **Pre-Market**: Reacts to overnight news, earnings reports (released before open)
- **Regular Hours**: Highest liquidity, tightest spreads
- **After-Hours**: Lower volume, wider spreads, earnings call reactions

**Holidays**: Market closed on US federal holidays (future enhancement: holiday calendar)

---

## Alpha Vantage Integration

**Endpoint**: `https://www.alphavantage.co/query`

**Key Parameters**: `function=TIME_SERIES_INTRADAY`, `symbol`, `interval` (1min/5min/15min/30min/60min), `extended_hours=true`, `outputsize` (compact/full), `apikey`

**Response**: Meta Data (symbol, interval, timezone) + Time Series with OHLCV data keyed by timestamp

### Rate Limits

| Tier | Calls/Day | Calls/Minute | Cost |
|------|-----------|--------------|------|
| Free | 25 | 5 | $0 |
| Premium | Unlimited | 75 | $50/month |

**Handling**: Cache in Redis (5 min TTL), fallback to regular hours if rate limited

---

## Security Considerations

**API Key Management**: Store in `.env` (gitignored), loaded into the backend container at startup.

**Data Validation**: Validate timestamps (4:00 AM - 8:00 PM ET), verify positive price/volume values, sanitize symbol input

---

## Performance Considerations

**Caching**: Redis key `extended_hours:{symbol}:{interval}:latest`, 5-minute TTL

**Optimization**: Background refresh for popular symbols, parallel regular + extended requests, progressive loading

---

## Testing Strategy

**Unit Tests** (`test_extended_hours_service.py`):
- `test_classify_pre_market`: 08:15 ET → "pre_market"
- `test_classify_regular_hours`: 14:30 ET → "regular"
- `test_classify_after_hours`: 18:45 ET → "after_hours"
- `test_classify_closed`: 21:00 ET → "closed"
- `test_split_by_session`: Data correctly split into 3 session arrays

**Integration Tests** (`chart-extended-hours.test.tsx`):
- Session toggle filters data correctly (All/Pre/Regular/After)
- Chart colors match session (blue pre-market, green/red regular, orange after-hours)

**Manual Testing**: Fetch AAPL/TSLA/MSFT extended data, verify session time ranges, toggle buttons, color-coding, rate limit handling, mobile responsiveness

---

## Acceptance Criteria

### Must Have (MVP)

- [x] Backend fetches extended hours data from Alpha Vantage
- [x] Data split into 3 sessions (pre-market, regular, after-hours)
- [x] New API endpoint: `GET /api/market/price/{symbol}/extended`
- [x] Frontend session toggle buttons (All, Pre, Regular, After)
- [x] Chart displays filtered data based on selected session
- [x] Color-coded candlesticks by session
- [x] Caching with 5-minute TTL (reduce API calls)
- [x] Error handling (rate limits, API errors)

### Nice to Have (Future)

- [ ] Automatic session detection (show current session by default)
- [ ] Volume profile by session (compare liquidity)
- [ ] Gap analysis (overnight gap between after-hours close and pre-market open)
- [ ] Holiday calendar (disable extended hours on market holidays)
- [ ] Real-time streaming (WebSocket) for live extended hours data
- [ ] Alerts for significant pre-market moves (>5% price change)

---

## Risks & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Alpha Vantage rate limits | High | High | Aggressive caching (5 min), fallback to regular hours |
| API cost escalation | Medium | Medium | Monitor usage, upgrade to Premium only if needed |
| Data accuracy concerns | High | Low | Validate against Bloomberg/Reuters, user feedback loop |
| Session classification errors | Medium | Low | Comprehensive unit tests, edge case handling |
| User confusion (3 session toggles) | Low | Medium | Clear UI labels, tooltips, onboarding guide |

---

## Rollout Plan

**Week 1**: Alpha Vantage integration (Day 1-2), API endpoint + caching (Day 3), Frontend session toggle (Day 4-5), Chart styling (Day 6)

**Week 2**: Testing + bug fixes (Day 1-2), Documentation (Day 3), Deploy + user testing (Day 4-5)

**Deployment Strategy**:
1. **Alpha**: Test environment, free tier (25/day), 5-10 users
2. **Beta**: 50% users (A/B test), upgrade to Premium if needed
3. **GA**: 100% rollout, onboarding education

**Monitoring**: API call count, session toggle distribution, errors, user engagement, cost per call

---

## Dependencies

**External**: Alpha Vantage API (Free: 25/day, Premium: $50/mo)

**Libraries**: `aiohttp` (async HTTP), `zoneinfo` (stdlib), existing lightweight-charts (frontend)

---

## Success Metrics

### Quantitative

- **Target**: 30% of active users view extended hours data within 30 days
- **Session Toggle Engagement**: >50% of users click session toggles
- **API Success Rate**: >99% (accounting for rate limits)
- **User Retention**: Extended hours users have 20% higher retention

### Qualitative

- Users report better understanding of overnight price movements
- Positive feedback on session toggle UX
- Traders identify more pre-market trading opportunities
- Reduced requests for "add pre-market data" in feedback

---

## Future Enhancements

1. **Level 2 Pre-Market Quotes**: Real-time bid/ask spreads
2. **Earnings Calendar Integration**: Highlight pre-market earnings reports
3. **News Feed by Session**: Show news articles that triggered moves
4. **Gap Scanner**: Identify stocks with largest overnight gaps
5. **Volume Analysis**: Compare pre/regular/after-hours volume
6. **Social Sentiment**: Track Twitter/Reddit buzz during extended hours

---

## References

- Alpha Vantage Documentation: https://www.alphavantage.co/documentation/
- Intraday Extended Hours API: https://www.alphavantage.co/documentation/#intraday-extended
- US Stock Market Hours: https://www.nasdaq.com/stock-market-trading-hours-for-nasdaq
- Trading Sessions Guide: https://www.investopedia.com/terms/e/extended_trading.asp
- Existing Market Data API: `/backend/src/api/market_data.py`
- yfinance Utils: `/backend/src/core/utils/yfinance_utils.py`
