# Financial Agent - Comprehensive Research Summary

## 1. LOGIN CREDENTIALS

**Default Test User**:
- **Username**: `admin`
- **Password**: `<password>`
- **Role**: Admin (has access to Health dashboard)

Location found: `/CLAUDE.md` line 78
```
Login with credentials (admin/<password>)
```

**Authentication Flow**:
- Username + Password authentication
- JWT token-based (Bearer tokens)
- Refresh token support
- Also supports email/phone verification for registration

---

## 2. AVAILABLE FEATURES & ROUTES

### Frontend Pages (Main Navigation Tabs)

| Feature | Route/Tab | Component | Access Level |
|---------|-----------|-----------|--------------|
| **Chat/Platform** | `/` (chat tab) | `EnhancedChatInterface.tsx` | All users |
| **Portfolio Dashboard** | `/` (portfolio tab) | `PortfolioDashboard.tsx` | All users |
| **Feedback & Roadmap** | `/` (feedback tab) | `FeedbackPage.tsx` | All users |
| **Transaction History** | `/` (transactions tab) | `TransactionHistory.tsx` | All users |
| **Health Dashboard** | `/` (health tab - admin only) | `HealthPage.tsx` | Admin only |

### Backend API Endpoints

#### Authentication (`/api/auth`)
- `POST /api/auth/send-code` - Send verification code
- `POST /api/auth/login` - Login with username/password
- `POST /api/auth/register` - Register new user
- `POST /api/auth/verify-code` - Verify code
- `POST /api/auth/refresh` - Refresh JWT token
- `POST /api/auth/logout` - Logout (revoke refresh token)
- `POST /api/auth/reset-password` - Reset password

#### Chat (`/api/chat`)
- `GET /api/chat/chats` - List user's chats (paginated)
- `POST /api/chat/message` - Send message (streaming)
- `GET /api/chat/{chat_id}` - Get chat details
- `PUT /api/chat/{chat_id}` - Update chat
- `DELETE /api/chat/{chat_id}` - Delete chat
- `PUT /api/chat/{chat_id}/ui-state` - Update UI state

#### Portfolio (`/api/portfolio`)
- `GET /api/portfolio/holdings` - Get current positions from Alpaca
- `GET /api/portfolio/summary` - Get portfolio summary (value, P&L)
- `GET /api/portfolio/history` - Get portfolio value history with markers
- `GET /api/portfolio/orders` - Get order execution records
- `POST /api/portfolio/analyze` - Trigger portfolio analysis

#### Watchlist (`/api/watchlist`)
- `POST /api/watchlist` - Add symbol to watchlist
- `GET /api/watchlist` - Get user's watchlist
- `DELETE /api/watchlist/{watchlist_id}` - Remove from watchlist
- `POST /api/watchlist/analyze` - Trigger watchlist analysis (5-min intervals)

#### Feedback (`/api/feedback`)
- `POST /api/feedback/upload-image` - Upload feedback image
- `POST /api/feedback` - Create feedback item
- `GET /api/feedback` - List feedback (filtered by type)
- `PUT /api/feedback/{id}` - Update feedback status
- `POST /api/feedback/{id}/vote` - Vote on feedback
- `POST /api/feedback/{id}/comment` - Add comment to feedback

#### Credits/Transactions (`/api/credits`)
- `GET /api/credits/balance` - Get user's credit balance
- `GET /api/credits/transactions` - Get transaction history (paginated)

#### Market Data (`/api/market-data`)
- `GET /api/market-data/prices/{symbol}` - Get price data with intervals
- `GET /api/market-data/search` - Search for stocks

#### LLM Models (`/api/llm-models`)
- `GET /api/llm-models` - List available models
- `POST /api/llm-models/analyze` - Analyze with specific model

#### Admin (`/api/admin`) - Admin only
- `GET /api/admin/health` - Health check with system metrics
- `GET /api/admin/system-metrics` - Kubernetes pod/node metrics

#### Health (`/api/health`)
- `GET /api/health` - Basic health check

---

## 3. WORKFLOWS - STEP-BY-STEP USER FLOWS

### Workflow 1: Login Flow
**URL**: `http://localhost:3000`

1. User arrives at Login Page
2. Enters username in "Username" field (id: `login-username`)
3. Enters password in "Password" field (id: `login-password`)
4. Clicks "Sign In" button
5. Frontend calls `POST /api/auth/login` with credentials
6. Backend returns JWT token + refresh token
7. Frontend stores tokens in localStorage (via `authStorage`)
8. User redirected to main app (Platform/Chat tab by default)

**Alternative Flows**:
- **Register**: Click "Don't have an account? Register →" → Email verification flow
- **Forgot Password**: Click "Forgot password?" → Email verification flow

---

### Workflow 2: Chat/Platform Analysis
**URL**: `http://localhost:3000` (Platform tab)

1. User lands on `EnhancedChatInterface`
2. **Select Symbol**:
   - Click symbol search field
   - Type stock symbol (e.g., "AAPL")
   - Select from search results
   - Symbol + timeframe chart appears
3. **Send Message**:
   - Type message in chat input (bottom)
   - Click send button
   - Connects to `/api/chat/message` (streaming)
   - Assistant's analysis appears in chat history
   - Chat ID auto-created if new
4. **Quick Analysis Buttons**:
   - Fibonacci Analysis
   - Trend Analysis
   - Other analysis types
5. **View History**:
   - Left sidebar shows chat list
   - Click chat to reload conversation

**Key Components**:
- `ChatInput` - Message input field
- `ChatMessages` - Conversation display
- `ChatSidebar` - Chat history list
- `ChartPanel` - Price chart with analysis overlays

---

### Workflow 3: Portfolio Dashboard
**URL**: `http://localhost:3000` (Portfolio tab)

1. User lands on `PortfolioDashboard`
2. **View Portfolio**:
   - Top shows portfolio value (auto-refreshed)
   - Shows total P&L (Profit/Loss) and percentage
   - Real-time data from Alpaca API
3. **Time Period Selection**:
   - Click "1D", "1M", "1Y", or "All" buttons
   - Chart updates to show selected period
4. **View Orders**:
   - Scroll down to "Order Execution Records" table
   - Shows all BUY/SELL orders placed by portfolio agent
   - Columns: Time, Symbol, Side, Qty, Status, Filled Qty, Avg Price, Analysis ID
5. **View Watchlist** (bottom):
   - Shows symbols being monitored
   - Add new symbols for auto-analysis
   - Remove symbols from watchlist
   - Trigger manual analysis
6. **Analysis Sidebar**:
   - Right sidebar shows portfolio agent's analysis history
   - Click chat to view detailed messages
   - Read-only (shows decision rationale)

**Key Components**:
- `PortfolioChart` - TradingView Lightweight Chart
- `WatchlistPanel` - Symbol management
- `ChatSidebar` - Analysis history (read-only)
- `ChatMessagesModal` - Shows full analysis conversation

---

### Workflow 4: Feedback & Roadmap
**URL**: `http://localhost:3000` (Feedback tab)

1. User lands on `FeedbackPage`
2. **Submit Feedback**:
   - Click "Submit Feedback" button
   - Opens `SubmitFeedbackForm` modal
   - Fill: Title, Description, Type (Feature/Bug)
   - Optional: Upload image (goes to OSS/S3)
   - Click submit
   - API: `POST /api/feedback`
3. **View Leaderboards**:
   - Left: Feature requests (sorted by votes)
   - Right: Bug reports (sorted by votes)
   - Each shows: Title, Vote count, Comment count, Created time
4. **Vote on Feedback**:
   - Click item to open `FeedbackDetailView`
   - See full description + image
   - Click upvote/downvote button
   - API: `POST /api/feedback/{id}/vote`
5. **Comment on Feedback**:
   - Open feedback detail
   - Scroll to comments section
   - Type comment + click submit
   - API: `POST /api/feedback/{id}/comment`

**Key Components**:
- `SubmitFeedbackForm` - Feedback submission modal
- `FeedbackLeaderboard` - List view (feature/bug)
- `FeedbackDetailView` - Detail modal with votes/comments

---

### Workflow 5: Transaction History
**URL**: `http://localhost:3000` (Transactions tab)

1. User lands on `TransactionHistory`
2. **Filter Transactions**:
   - Default: "All Transactions"
   - Dropdown filters: Completed, Pending, Failed
   - Shows paginated list
3. **View Transaction**:
   - Status badge (green/orange/red)
   - Model name used (e.g., "qwen-plus")
   - Token count (input/output/total) if completed
   - Date/time
   - Cost in credits
4. **Pagination**:
   - Shows "Page X of Y"
   - Previous/Next buttons
   - Total transaction count

**Key Data**:
- Each transaction shows: ID, Status, Model, Tokens, Date, Cost
- Tokens only shown if COMPLETED
- Cost shows estimated for PENDING

---

### Workflow 6: Admin Health Dashboard
**URL**: `http://localhost:3000` (Health tab - Admin only)

1. **Access** (requires `admin` user or admin):
   - Only visible in navigation if user is admin
   - Tab only shows when `isAdmin === true`
2. **View System Health**:
   - Overall health status (green/yellow/red)
   - Database statistics (collections, document counts, sizes)
3. **View Pod Metrics** (Kubernetes):
   - Pod names, CPU/Memory usage
   - CPU & Memory percentages
   - Node assignment
   - Resource requests/limits
4. **View Node Metrics** (Kubernetes):
   - Node names
   - CPU/Memory usage vs capacity
   - Percentage utilization
5. **Auto-refresh**:
   - Metrics update every 30 seconds
   - Shows last updated timestamp

**Key Components**:
- System health status
- Database statistics table
- Pod metrics table
- Node metrics table
- Mock data for local dev (when K8s unavailable)

---

## 4. UI ELEMENT SELECTORS (Playwright/Automation)

### Login Page Elements

```
login-username        input#login-username          Username field
login-password        input#login-password          Password field
sign-in-button        button (text: "Sign In")      Submit button
forgot-password       button (text: "Forgot")       Forgot password link
register-link         button (text: "Register")     Register link
```

### Main Navigation (Header)

```
health-tab            button (text: "Health")       Admin-only health tab
chat-tab              button (text: "Platform")     Chat/Platform tab
portfolio-tab         button (text: "Portfolio")    Portfolio dashboard tab
feedback-tab          button (text: "Feedback")     Feedback page tab
transactions-tab      button (text: "Transactions") Transaction history tab
logout-button         button (text: "Logout")       Logout button
user-display          span (text: username)         Logged-in username
credit-balance        CreditBalance component       Shows credit balance
```

### Chat Interface (Platform Tab)

```
symbol-input          Search input field            Stock symbol search
symbol-search-results List items                   Autocomplete results
chat-input            textarea or input            Message input field
send-button           button (contains send icon)   Send message
chat-messages         div.chat-messages             Message history container
chat-sidebar          div.chat-sidebar              Chat history list
chart-panel           ChartPanel component          Price chart display
fibonacci-button      button (text: "Fibonacci")    Fibonacci analysis
trend-button          button (text: "Trend")        Trend analysis
model-selector        select/dropdown               LLM model selection
```

### Portfolio Dashboard

```
portfolio-value       div (large number)            Current portfolio value
portfolio-pl          div (P/L amount)              Profit/Loss display
period-buttons        button group (1D/1M/1Y/All)   Time period selector
refresh-button        button (text: "Refresh")      Refresh data
portfolio-chart       PortfolioChart component     TradingView chart
orders-table          table.orders                  Order execution records
orders-symbol         td (symbol column)            Stock symbol in order
orders-side           span (BUY/SELL badge)         Order direction
watchlist-panel       WatchlistPanel component     Symbol watchlist
watchlist-input       input (symbol entry)          Add symbol field
watchlist-add         button (add icon)             Add to watchlist
watchlist-remove      button (remove icon)          Remove from watchlist
watchlist-analyze     button (text: "Analyze")      Trigger analysis
analysis-sidebar      ChatSidebar component        Analysis history
```

### Feedback Page

```
submit-feedback-btn   button (text: "Submit")       Open feedback form
feedback-form-modal   SubmitFeedbackForm            Form modal
feedback-title        input#feedback-title          Feedback title field
feedback-description  textarea#feedback-desc       Description field
feedback-type-select  select (Feature/Bug)         Type selector
feedback-image-upload input[type=file]             Image upload field
feedback-submit       button (form submit)         Submit feedback button
feature-leaderboard   FeedbackLeaderboard          Feature requests list
bug-leaderboard       FeedbackLeaderboard          Bug reports list
feedback-item         div.feedback-item            Single feedback item
feedback-votes        span (vote count)            Vote count display
feedback-detail       FeedbackDetailView           Detail modal
vote-upvote           button (thumbs up)           Upvote button
vote-downvote         button (thumbs down)         Downvote button
comment-input         textarea (comment text)      Comment input field
comment-submit        button (send comment)        Submit comment button
```

### Transaction History Page

```
transaction-filter    select (filter dropdown)     Status filter
transaction-list      div.transaction-list         Transactions container
transaction-item      div.transaction-item         Single transaction
transaction-status    span.status-badge            Status badge
transaction-model     span (model name)            Model used
transaction-tokens    span (token count)           Token statistics
transaction-cost      span (large cost value)      Credit cost display
pagination-prev       button (text: "Previous")    Previous page button
pagination-next       button (text: "Next")        Next page button
pagination-info       span (page info)             Current page display
```

### Health Dashboard (Admin)

```
health-status         div.health-status            Overall status indicator
database-stats-table  table.database-stats         Database statistics
database-collection   td (collection name)         Collection name cell
database-count        td (document count)          Document count cell
pods-metrics-table    table.pods-metrics           Pod metrics table
pod-name              td (pod name)                Pod name cell
pod-cpu               td (CPU usage)               CPU usage cell
pod-memory            td (Memory usage)            Memory usage cell
nodes-metrics-table   table.nodes-metrics          Node metrics table
node-name             td (node name)               Node name cell
node-cpu              td (CPU usage)               CPU usage cell
refresh-metrics       button (refresh icon)        Refresh metrics button
```

---

## 5. KEY TECHNICAL DETAILS

### Environment Access
- **Dev/Local**: `http://localhost:3000` (frontend), `http://localhost:8000` (API)
- **Test (K8s)**: `http://localhost:3000`
- **Start locally**: `make dev`

### Database
- **Backend**: MongoDB (holds chats, users, watchlist, feedback)
- **Cache**: Redis (token blacklist, rate limiting)
- **Trading**: Alpaca API (positions, orders, prices)

### Authentication
- JWT tokens (Bearer in Authorization header)
- Access token + refresh token pair
- Tokens stored in localStorage (authService)
- Admin check: `user.is_admin || user.username === "admin"`

### Key Hooks (React)
- `useQuery` - Fetch data (React Query)
- `useMutation` - Submit data
- `useAnalysis` - Chat analysis mutations
- `useWatchlist` - Watchlist management
- `usePortfolioHistory` - Portfolio chart data
- `useTransactionHistory` - Transaction pagination

### Services
- `authService` - Login/logout, token management
- `marketService` - Price data, symbol search
- `portfolioApi` - Portfolio data (Alpaca integration)
- `feedbackApi` - Feedback CRUD

---

## 6. IMPORTANT TESTING NOTES

1. **Login credential**: Always use `admin` / `<password>` for testing
2. **Admin access**: Only `admin` user sees Health tab
3. **Portfolio data**: Comes from Alpaca paper trading (real API)
4. **Watchlist**: 5-minute analysis cycles (auto-trigger)
5. **Credits**: Deducted per LLM API call (transaction history tracks it)
6. **Rate limiting**: Multiple endpoints have rate limits
7. **WebSocket**: Chat uses HTTP streaming (not WebSocket)
8. **Image uploads**: OSS/S3 presigned URLs (async upload)

---

## 7. FEATURE SUMMARY TABLE

| Feature | Purpose | Entry Point | Key Endpoint |
|---------|---------|-------------|--------------|
| Chat/Analysis | Stock analysis via AI | Platform tab | `POST /api/chat/message` |
| Portfolio | Alpaca account view + agent | Portfolio tab | `GET /api/portfolio/*` |
| Watchlist | Auto-monitor symbols | Portfolio → Watchlist | `POST /api/watchlist` |
| Feedback | Community roadmap voting | Feedback tab | `POST /api/feedback` |
| Transactions | Credit spending history | Transactions tab | `GET /api/credits/transactions` |
| Health | System monitoring (admin) | Health tab | `GET /api/admin/health` |

---

## 8. PLAYWRIGHT TEST SELECTORS - READY TO USE

### Complete selector mapping for automation:

**Login Form**:
- Username: `input#login-username`
- Password: `input#login-password`
- Submit: `button:has-text("Sign In")`

**Navigation**:
- Platform: `button:has-text("Platform")`
- Portfolio: `button:has-text("Portfolio")`
- Feedback: `button:has-text("Feedback")`
- Transactions: `button:has-text("Transactions")`
- Health: `button:has-text("Health")`
- Logout: `button:has-text("Logout")`

**Chat Page**:
- Symbol input: `input[placeholder*="symbol"]`
- Chat input: `textarea[placeholder*="message"]`
- Send button: `button[aria-label*="send"]`

**Portfolio**:
- Period buttons: `button:has-text("1D")`, `button:has-text("1M")`, etc.
- Refresh: `button:has-text("Refresh")`
- Orders table: `table` (nth occurrence)
- Watchlist input: `input[placeholder*="symbol"]`

**Feedback**:
- Submit button: `button:has-text("Submit Feedback")`
- Title input: `input[placeholder*="title"]`
- Type select: `select`

