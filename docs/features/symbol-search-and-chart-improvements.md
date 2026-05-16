---
title: Symbol Search and Chart Visualization Improvements
status: in-progress
version: backend@0.8.x, frontend@0.10.x
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/src/api/market/search.py
  - backend/src/api/market/prices.py
  - frontend/src/components/Chart/
---

# Symbol Search and Chart Visualization Improvements

> Phase 1 (deduplication, match_type ranking, OHLC tooltip) shipped. Phase 2
> backend date-range support (`start_date` / `end_date` in analysis endpoints)
> shipped; matching frontend `DateRangePicker` component not yet implemented.
> Phase 3 candlestick / volume overlay still planning.

## Context

The current symbol search and chart visualization have several UX issues:
1. Search returns duplicates (AAPL appears multiple times)
2. Irrelevant results (Apple Hospitality REIT when searching "apple")
3. Hardcoded symbol mappings (not scalable)
4. Chart tooltip only shows close price (no OHLC data)
5. No custom date range selection
6. Analysis buttons use default periods, not user-selected ranges

## Problem Statement

### Symbol Search Issues

**Root Cause:**
- `yfinance.search()` returns ALL matching tickers across all exchanges without filtering
- Same company appears on multiple exchanges (AAPL on NMS, FRA, NEO, etc.)
- No relevance ranking beyond simple string matching
- Hardcoded mappings like `"meituan" → "3690.HK"` are not scalable

**Current Flow:**
```
User types "apple"
  → yfinance.search("apple")
  → Returns: AAPL (NMS), AAPL (NEO), 48T.F (FRA), AAPL.NE, etc.
  → Frontend shows all results (duplicates + irrelevant)
```

### Chart Visualization Issues

**Current Limitations:**
- Tooltip only shows: `"Jul 17, 2025 | $209.78"`
- No OHLC (Open, High, Low, Close) information
- No volume data
- No color coding for candle direction
- Fixed time periods (1H, 1D, 1W, 1M)
- No custom date range selection
- Analysis buttons use backend defaults, not user selection

## Proposed Solution

### Phase 1: Quick Wins (2-3 days)

#### 1.1 Fix Symbol Search Deduplication

**Backend** (`market_data.py`): Deduplicate by company name, prioritize US exchanges (NMS, NAS, NYQ), sort by relevance score, limit to top 10.

**Result**: "apple" → AAPL (NMS) only, duplicates and low-relevance removed.

#### 1.2 Add OHLC to Chart Tooltip

**Frontend** (`Chart.tsx`): Update tooltip to show Open/High/Low/Close with color coding (green ↑, red ↓) and formatted volume.

#### 1.3 Show Date Range Labels

**Frontend**: Display "Showing data from {start} to {end} ({days} days)" below chart.

---

### Phase 2: Date Range Selection (3-4 days)

#### 2.1 Add Custom Date Range Picker UI

**Design**: HTML5 date inputs with quick presets (1W, 1M, 3M, 6M, 1Y, YTD, Max)

**Component**: `DateRangePicker.tsx` - Start/end date inputs, preset buttons, Apply button

#### 2.2 Update Backend APIs for Date Range

**Schema** (`analysis_models.py`): Add optional `start_date`, `end_date` fields to `AnalysisRequest`. Calculate period from date range (7d→5y based on days).

**Endpoints**: Update Fibonacci, Stochastic, Fundamental to accept date range parameters with fallback to period.

#### 2.3 Wire Analysis Buttons to Date Range

**Frontend** (`AnalysisButtons.tsx`): Pass `start_date`/`end_date` to analysis API calls. Display "Analysis will use data from {start} to {end}".

---

### Phase 3: Better Symbol Search (4-5 days)

#### 3.1 Integrate Financial Modeling Prep (FMP) API

**Why FMP?**: Clean deduplicated data, 250 req/day free, $15/mo production, better quality than yfinance.

| Data Source | Free Tier | Quality | Cost | Verdict |
|-------------|-----------|---------|------|---------|
| yfinance | Unlimited | Poor | Free | ❌ Current |
| FMP API | 250/day | Excellent | $15/mo | ✅ Recommended |
| IEX Cloud | 50k/mo | Good | $9/mo | ✅ Alternative |

**Implementation** (`SymbolSearchService`):
1. Check Redis cache (24hr TTL)
2. Try FMP API (primary)
3. Fallback to yfinance
4. Calculate relevance score (exact match → starts with → contains → fuzzy)

**Config**: `FMP_API_KEY`, `SYMBOL_SEARCH_CACHE_TTL`

#### 3.2 Add Symbol Alias Database

**Purpose**: Support alternate names (e.g., "meituan" → "3690.HK") without hardcoding.

**Schema** (`SymbolAlias`): alias, symbol, exchange, company_name, priority, source, verified

**Search Flow**: Check alias collection first → if match, return target symbol → else normal search.

#### 3.3 Admin Interface for Symbol Aliases

**API**: `POST/GET/DELETE /api/admin/aliases` (admin only)

**Frontend**: `AdminAliasesPage.tsx` - Create/list/delete aliases table.

---

## Implementation Roadmap

### Week 1: Quick Wins

**Days 1-2: Symbol Search Fixes**
- [ ] Implement deduplication logic
- [ ] Add exchange prioritization
- [ ] Limit results to top 10
- [ ] Add unit tests
- [ ] Deploy and verify

**Days 3: Chart OHLC Enhancement**
- [ ] Update frontend tooltip formatter
- [ ] Add color coding (green/red)
- [ ] Format volume display
- [ ] Test with various symbols
- [ ] Deploy and verify

### Week 2: Date Range Selection

**Days 4-5: UI Components**
- [ ] Create DateRangePicker component
- [ ] Add quick preset buttons
- [ ] Integrate with chart state
- [ ] Add date range labels
- [ ] Test on mobile

**Days 6-7: Backend API Updates**
- [ ] Add start_date/end_date to analysis schemas
- [ ] Update Fibonacci endpoint
- [ ] Update Stochastic endpoint
- [ ] Update Fundamental endpoint
- [ ] Add date range validation
- [ ] Write integration tests

**Day 8: Integration**
- [ ] Wire analysis buttons to date range
- [ ] Add loading states
- [ ] Handle errors gracefully
- [ ] E2E testing
- [ ] Deploy to staging

### Week 3: Better Search Integration

**Days 9-10: FMP API Integration**
- [ ] Sign up for FMP API account
- [ ] Implement FMP search service
- [ ] Add Redis caching layer
- [ ] Implement fallback logic
- [ ] Load test (rate limits)
- [ ] Deploy with feature flag

**Days 11-12: Symbol Aliases**
- [ ] Create MongoDB collection
- [ ] Implement alias repository
- [ ] Add alias search logic
- [ ] Create admin API endpoints
- [ ] Build admin UI
- [ ] Seed with common aliases

## Success Metrics

### Symbol Search Quality
- **Duplicate Rate**: < 5% (currently ~30%)
- **Relevance Score**: > 90% for top result
- **Search Speed**: < 200ms p95

### Chart UX
- **Tooltip Information**: OHLC + Volume visible
- **Date Range Adoption**: > 30% of analysis uses custom range
- **Analysis Accuracy**: Uses correct date range 100% of time

### Alias Coverage
- **Common Aliases**: Top 100 stocks have alternate names
- **Admin Usage**: > 50 aliases created in first month
- **Search Success Rate**: > 95% (alias + regular search)

## Migration Strategy

### Phase 1 (No Breaking Changes)
- Deploy symbol search improvements
- Add OHLC tooltip
- Add date labels
- **No data migration needed**

### Phase 2 (Additive Changes)
- Deploy date range picker
- Update APIs to accept optional date params
- **Backward compatible** (defaults to existing behavior)

### Phase 3 (New Services)
- Deploy FMP integration with feature flag
- Create symbol_aliases collection
- Roll out to admins first
- Gradual rollout to all users

## Testing Strategy

### Unit Tests
- Symbol search deduplication logic
- OHLC tooltip formatting
- Date range validation
- Alias matching logic

### Integration Tests
- End-to-end symbol search flow
- Analysis with custom date range
- FMP API integration with fallback
- Alias CRUD operations

### Manual Testing
- Search for common stocks (AAPL, TSLA, MSFT)
- Search for international stocks (3690.HK, 600519.SS)
- Test date range picker on mobile
- Test analysis with various date ranges
- Verify OHLC data accuracy

## Risks and Mitigation

### Risk 1: FMP API Rate Limits
**Mitigation**:
- Redis caching (24hr TTL)
- Fallback to yfinance
- Monitor usage via logging

### Risk 2: Date Range Performance
**Mitigation**:
- Limit max range (e.g., 5 years)
- Show loading indicators
- Cache analysis results

### Risk 3: Breaking Changes
**Mitigation**:
- All changes backward compatible
- Feature flags for new functionality
- Gradual rollout

## Follow-Up Work

### Phase 4 (Future Enhancements)
- Fuzzy search with Levenshtein distance
- User-contributed aliases (with moderation)
- Multiple chart comparison
- Technical indicator overlays
- Export chart as image
- Share analysis links

## Questions for Discussion

1. **FMP API Cost**: Comfortable with $15/month for production?
2. **Date Range Limits**: Should we cap at 5 years or allow "Max"?
3. **Alias Moderation**: Admin-only or community-driven with approval?
4. **Mobile UX**: Native date picker or custom component?
5. **Analytics**: What metrics should we track for search quality?

---

**Last Updated**: 2025-10-11
**Document Owner**: Engineering Team
**Reviewers**: Product, Design, Backend Lead, Frontend Lead
