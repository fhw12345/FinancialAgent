# Version Compatibility Matrix

This document tracks compatibility between Financial Agent components across different versions.

## Current Versions

| Component | Version | Status | Released |
|-----------|---------|--------|----------|
| Backend | 0.8.8 | ✅ Current | 2025-12-14 |
| Frontend | 0.11.0 | ✅ Current | 2025-11-27 |

## Compatibility Table

### Backend ↔ Frontend

| Backend | Frontend | Compatible | Notes |
|---------|----------|------------|-------|
| 0.8.8 | 0.11.0 | ✅ Yes | Module restructure, context compaction, get_stock_quote tool |
| 0.8.3 | 0.11.0 | ✅ Yes | Portfolio analysis with structured output, order optimization |
| 0.8.2 | 0.11.0 | ✅ Yes | Auto-inject selected symbol from UI |
| 0.8.1 | 0.10.1 | ✅ Yes | Watchlist symbol validation fixes |
| 0.8.0 | 0.10.0 | ✅ Yes | Portfolio-aware analysis, tool execution progress |
| 0.7.1 | 0.10.1 | ✅ Yes | OSS presigned URLs, batch streaming |
| 0.7.0 | 0.10.0 | ✅ Yes | Real-time tool execution streaming |
| 0.6.2 | 0.8.15 | ✅ Yes | Market movers caching, API URL standardization |
| 0.5.x | 0.8.x | ✅ Yes | Admin dashboard, agent mode toggle |
| 0.4.x | 0.7.x | ✅ Yes | Dual-token JWT auth, chat delete |
| 0.4.1 | 0.4.1 | ✅ Yes | Bug fixes - MongoDB URL parsing, API URL fallback |
| 0.1.0 | 0.1.0 | ✅ Yes | Initial release - full compatibility |

### Component ↔ Infrastructure

| Component | MongoDB | Redis | Kubernetes | Python | Node.js |
|-----------|---------|-------|------------|--------|---------|
| Backend 0.8.x | 7.0+ | 7.2+ | 1.28+ (ACK/AKS) | 3.12+ | N/A |
| Frontend 0.11.x | N/A | N/A | 1.28+ (ACK/AKS) | N/A | 18+ |
| Backend 0.7.x | 7.0+ | 7.2+ | 1.28+ | 3.12+ | N/A |
| Frontend 0.10.x | N/A | N/A | 1.28+ | N/A | 18+ |

### External Services

| Component | Tencent Cloud SES | Alibaba DashScope | Alpha Vantage | Alpaca |
|-----------|-------------------|-------------------|---------------|--------|
| Backend 0.8.x | Required (email) | Required (LLM) | Required (market data) | Required (trading) |
| Backend 0.7.x | Required (email) | Required (LLM) | Required (market data) | Optional |
| Backend 0.5.x | Required (email) | Required (LLM) | N/A (yfinance) | N/A |
| Backend 0.4.x | Required (email) | Required (LLM) | N/A | N/A |

## API Contract Versions

### v0.8.x Contracts

**Portfolio Endpoints** (NEW in 0.8.x):
- `GET /api/portfolio/summary` - Portfolio summary with holdings
- `GET /api/portfolio/holdings` - Current holdings list
- `GET /api/portfolio/transactions` - Transaction history with filtering
- `GET /api/portfolio/orders` - Order execution records
- `GET /api/portfolio/watchlist` - Watchlist symbols
- `POST /api/portfolio/watchlist` - Add symbol to watchlist
- `DELETE /api/portfolio/watchlist/{symbol}` - Remove from watchlist
- `POST /api/portfolio/analyze` - Trigger portfolio analysis
- `GET /api/portfolio/chat-history` - Analysis chat history

**Chat Endpoints** (Enhanced in 0.7.x):
- `POST /api/chat/message` - Send message with tool execution streaming
- `GET /api/chat/chats` - List user's chats
- `GET /api/chat/chats/{chat_id}/messages` - Get chat messages
- `DELETE /api/chat/chats/{chat_id}` - Delete chat

**Authentication Endpoints**:
- `POST /api/auth/send-code` - Send verification code via email
- `POST /api/auth/verify-code` - Verify code and login
- `POST /api/auth/register` - Register with email verification
- `POST /api/auth/login` - Login with username/password
- `POST /api/auth/refresh` - Refresh access token
- `GET /api/auth/me` - Get current user

**Market & Analysis Endpoints**:
- `GET /api/health` - Health check
- `GET /api/market/search?q={query}` - Symbol search (Alpha Vantage)
- `GET /api/market/price/{symbol}` - Price data with interval/period
- `GET /api/market/movers` - Top gainers/losers (cached)
- `POST /api/analysis/fibonacci` - Fibonacci analysis
- `POST /api/analysis/stochastic` - Stochastic oscillator
- `POST /api/analysis/macro` - Macro sentiment analysis
- `POST /api/analysis/news-sentiment` - News sentiment

### v0.1.0 Contracts

**Endpoints**:
- `GET /api/health` - Health check
- `GET /api/market/search?q={query}` - Symbol search
- `GET /api/market/price/{symbol}?interval={interval}&period={period}` - Price data
- `POST /api/analysis/fibonacci` - Fibonacci analysis
- `GET /api/analysis/fundamentals/{symbol}` - Fundamental analysis
- `POST /api/analysis/stochastic` - Stochastic oscillator

**Data Types**:
- Interval: `"1d" | "1h" | "5m"`
- Period: `"1mo" | "3mo" | "6mo" | "1y" | "2y"`

## Breaking Changes History

### v0.4.1
- None (bug fix release)

### v0.4.0
- **Authentication Required**: All endpoints except `/api/health` now require authentication (JWT token)
- **MongoDB URL Format**: Cosmos DB requires query parameters in connection string
- **Email Service**: Tencent Cloud SES is now required (SMTP removed)

### v0.1.0
- None (initial release)

## Upgrade Paths

### From v0.4.0 to v0.4.1

**Backend**:
1. No schema changes required
2. Update image to `backend:test-v0.4.1`
3. Restart pods to apply MongoDB URL parsing fix

**Frontend**:
1. No API contract changes
2. Update image to `frontend:test-v0.4.1`
3. Restart pods to apply API URL fix

**Critical Fixes**:
- MongoDB database name now correctly parsed (strips query params)
- Frontend uses relative URLs (no more localhost:8000 fallback)

### From v0.1.0 to v0.4.1

**Breaking Changes**:
- Authentication endpoints added
- MongoDB connection URL must include database name
- Tencent Cloud SES configuration required

**Migration**:
1. Configure Tencent Cloud SES (API keys in Key Vault)
2. Update MongoDB connection string with database name
3. Build and deploy both frontend and backend v0.4.1
4. Test authentication flow end-to-end

## Version Support Policy

| Version Status | Support Duration | Updates |
|---------------|------------------|---------|
| Current (0.4.x) | Ongoing | Bug fixes + features |
| Previous Minor (0.3.x) | N/A | Not released |
| Older (0.1.x) | Unsupported | None |

## Testing Compatibility

Before deploying version combinations not listed above:

1. **API Contract Test**: Verify endpoint signatures match
2. **Integration Test**: Test critical user flows end-to-end
3. **Data Validation**: Ensure request/response schemas compatible
4. **Backward Compatibility**: Test older frontend with newer backend

## Reporting Incompatibility

If you discover an incompatible version combination:

1. Document the issue in [known-bugs.md](../troubleshooting/known-bugs.md)
2. Update this matrix with ❌ status
3. Add workaround or migration path
4. Tag issue with severity (critical/major/minor)

---

**Last Updated**: 2025-12-14
**Current Stable**: Backend v0.8.8 + Frontend v0.11.0
