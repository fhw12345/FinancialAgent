# Database Schema Documentation

> **Database**: Azure Cosmos DB for MongoDB API (v4.2)
> **Last Updated**: 2025-11-18
> **Version**: Reflects backend v0.7.0

## Overview

The Financial Agent platform uses **Azure Cosmos DB with MongoDB API** for persistence. The schema is defined using **Pydantic models** in `backend/src/models/` which enforce type safety and validation.

## Database Configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Provider** | Azure Cosmos DB for MongoDB API | Managed MongoDB-compatible service |
| **API Version** | 4.2 | |
| **Throughput Mode** | Shared Database Throughput | 400 RU/s minimum |
| **Database Name** | `_test` (test), `_prod` (prod) | |
| **Connection** | External Secrets → Azure Key Vault | `mongodb-connection-string-test` |

## Collections

### 1. `users` Collection

**Purpose**: User accounts with multi-auth support (email, phone, WeChat) and credit system integration.

**Pydantic Model**: `backend/src/models/user.py::User`

**Schema**:

| Field | Type | Required | Unique | Default | Description |
|-------|------|----------|--------|---------|-------------|
| `user_id` | string | ✅ | ✅ | auto-generated | Unique user identifier (`user_<uuid>`) |
| `email` | string \| null | ❌ | ✅ (if set) | null | Email address for email/password auth |
| `phone_number` | string \| null | ❌ | ✅ (if set) | null | Phone number with country code |
| `wechat_openid` | string \| null | ❌ | ✅ (if set) | null | WeChat OpenID for WeChat login |
| `username` | string | ✅ | ✅ | - | Display name and login username |
| `password_hash` | string \| null | ❌ | ❌ | null | Bcrypt hash (null for OAuth users) |
| `email_verified` | boolean | ✅ | ❌ | false | Email verification status |
| `is_admin` | boolean | ✅ | ❌ | false | Admin privileges flag |
| `created_at` | datetime | ✅ | ❌ | current UTC | Account creation timestamp |
| `last_login` | datetime \| null | ❌ | ❌ | null | Last login timestamp |
| `feedbackVotes` | array[string] | ✅ | ❌ | [] | List of feedback item IDs user voted for |
| `credits` | float | ✅ | ❌ | 1000.0 | Current credit balance (1元 = 100 credits) |
| `total_tokens_used` | integer | ✅ | ❌ | 0 | Lifetime total tokens consumed |
| `total_credits_spent` | float | ✅ | ❌ | 0.0 | Lifetime total credits spent |

**Indexes**:

```javascript
// Partial indexes (allow multiple NULL values)
db.users.createIndex(
  { "email": 1 },
  {
    unique: true,
    partialFilterExpression: { "email": { "$type": "string" } },
    name: "idx_email"
  }
)

db.users.createIndex(
  { "phone_number": 1 },
  {
    unique: true,
    partialFilterExpression: { "phone_number": { "$type": "string" } },
    name: "idx_phone_number"
  }
)

db.users.createIndex(
  { "wechat_openid": 1 },
  {
    unique: true,
    partialFilterExpression: { "wechat_openid": { "$type": "string" } },
    name: "idx_wechat_openid"
  }
)

db.users.createIndex({ "username": 1 }, { unique: true, name: "idx_username" })
```

**Notes**:
- **Multi-auth support**: Users can sign up with ANY ONE of email/phone/WeChat
- **Partial indexes**: Allow unlimited NULL values while enforcing uniqueness on actual values
- **Credit system**: Integrated for token-based economy (Backend v0.5.3)
- **Admin check**: Hardcoded "admin" OR `is_admin` flag

---

### 2. `chats` Collection

**Purpose**: Persistent chat conversations with UI state management.

**Pydantic Model**: `backend/src/models/chat.py::Chat`

**Schema**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `chat_id` | string | ✅ | auto-generated | Unique chat identifier (`chat_<uuid>`) |
| `user_id` | string | ✅ | - | Owner user ID (foreign key) |
| `title` | string | ✅ | "New Chat" | Chat title (auto-generated from first message) |
| `is_archived` | boolean | ✅ | false | Archive status |
| `ui_state` | object | ✅ | {} | Frontend UI state (symbol, interval, overlays) |
| `last_message_preview` | string \| null | ❌ | null | Preview of last message (200 chars max) |
| `created_at` | datetime | ✅ | current UTC | Chat creation timestamp |
| `updated_at` | datetime | ✅ | current UTC | Last update timestamp |
| `last_message_at` | datetime \| null | ❌ | null | Last message timestamp |

**UI State Schema** (`ui_state` object):

```typescript
{
  current_symbol: string | null,          // e.g., "AAPL", "NVDA"
  current_interval: string | null,        // e.g., "1d", "1h", "5m"
  current_date_range: {
    start: string | null,                 // ISO 8601 date
    end: string | null
  },
  active_overlays: {
    [tool_name]: {                        // e.g., "fibonacci", "stochastic"
      enabled: boolean,
      ...                                 // Tool-specific config
    }
  }
}
```

**Indexes**:

```javascript
// Compound index for list queries (Cosmos DB compatible)
db.chats.createIndex({ "user_id": 1, "is_archived": 1, "updated_at": -1 })
```

**Notes**:
- **Cosmos DB requirement**: Must sort by `updated_at` instead of `_id` (Backend v0.5.5 fix)
- **UI state**: Stores chart configuration for chat restoration
- **Title generation**: Auto-generated from first user message using LLM

---

### 3. `messages` Collection

**Purpose**: Chat message history with metadata for analysis results and tool executions.

**Pydantic Model**: `backend/src/models/message.py::Message`

**Schema**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `message_id` | string | ✅ | auto-generated | Unique message identifier (`msg_<uuid>`) |
| `chat_id` | string | ✅ | - | Parent chat ID (foreign key) |
| `role` | enum | ✅ | - | Message role: "user", "assistant", "system" |
| `content` | string | ✅ | - | Message text content |
| `source` | enum | ✅ | - | Message source: "user", "llm", "tool" |
| `timestamp` | datetime | ✅ | current UTC | Message creation timestamp |
| `metadata` | object | ✅ | {} | Message metadata (analysis results, token usage) |

**Message Metadata Schema** (`metadata` object):

```typescript
{
  // LLM metadata (assistant messages)
  model?: string,                         // e.g., "qwen-plus", "qwen-turbo"
  tokens?: number,                        // Total tokens (input + output)
  input_tokens?: number,                  // Prompt tokens
  output_tokens?: number,                 // Completion tokens
  transaction_id?: string,                // Credit transaction ID

  // Tool execution metadata (tool messages)
  selected_tool?: string,                 // e.g., "fibonacci", "stochastic"
  symbol?: string,                        // Stock symbol analyzed
  timeframe?: string,                     // Chart interval
  start_date?: string,                    // Analysis start date
  end_date?: string,                      // Analysis end date

  // Analysis results (compact metadata, not full arrays)
  raw_data?: {                            // Store parameters, not data arrays
    fibonacci_levels?: number[],          // [0.236, 0.382, 0.5, 0.618, 0.786]
    stochastic_k?: number,                // Latest K% value
    stochastic_d?: number,                // Latest D% value
    ...
  }
}
```

**Indexes**:

```javascript
// Compound index for chat message retrieval
db.messages.createIndex({ "chat_id": 1, "timestamp": 1 })

// Sparse index for transaction reconciliation
db.messages.createIndex(
  { "metadata.transaction_id": 1 },
  { sparse: true, name: "idx_transaction_id" }
)
```

**Notes**:
- **Metadata philosophy**: Store compact parameters, not large data arrays (~95% storage reduction)
- **Tool messages**: Store analysis metadata for chat restoration
- **Token tracking**: Links to credit transactions for reconciliation

---

### 4. `credit_transactions` Collection

**Purpose**: Token consumption tracking and credit accounting.

**Pydantic Model**: `backend/src/models/transaction.py::CreditTransaction`

**Schema**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `transaction_id` | string | ✅ | auto-generated | Unique transaction ID (`txn_<uuid>`) |
| `user_id` | string | ✅ | - | User ID (foreign key) |
| `chat_id` | string \| null | ❌ | null | Associated chat ID |
| `message_id` | string \| null | ❌ | null | Associated message ID |
| `type` | enum | ✅ | - | Transaction type: "usage", "purchase", "refund", "admin_adjustment" |
| `amount` | float | ✅ | - | Credit change (negative for usage, positive for purchase) |
| `balance_after` | float | ✅ | - | User balance after transaction |
| `model` | string \| null | ❌ | null | LLM model used (e.g., "qwen-plus") |
| `input_tokens` | integer \| null | ❌ | null | Input tokens consumed |
| `output_tokens` | integer \| null | ❌ | null | Output tokens consumed |
| `total_tokens` | integer \| null | ❌ | null | Total tokens (input + output) |
| `status` | enum | ✅ | "pending" | Transaction status: "pending", "completed", "failed" |
| `created_at` | datetime | ✅ | current UTC | Transaction creation timestamp |
| `completed_at` | datetime \| null | ❌ | null | Transaction completion timestamp |
| `metadata` | object | ✅ | {} | Additional transaction context |

**Indexes**:

```javascript
// Query by user and status
db.credit_transactions.createIndex({ "user_id": 1, "status": 1, "created_at": -1 })

// Reconciliation queries
db.credit_transactions.createIndex({ "message_id": 1 }, { sparse: true })
```

**Notes**:
- **Two-phase commit**: Transactions created as "pending", then "completed" after token counting
- **Safety net**: Prevents charging users if LLM call fails
- **Reconciliation**: Links to messages for token usage verification

---

### 5. `refresh_tokens` Collection

**Purpose**: JWT refresh token storage for secure authentication.

**Pydantic Model**: `backend/src/models/refresh_token.py::RefreshToken`

**Schema**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `token_id` | string | ✅ | auto-generated | Unique token identifier (UUID) |
| `user_id` | string | ✅ | - | Owner user ID (foreign key) |
| `token_hash` | string | ✅ | - | SHA-256 hash of refresh token |
| `expires_at` | datetime | ✅ | - | Token expiration timestamp |
| `created_at` | datetime | ✅ | current UTC | Token creation timestamp |
| `revoked` | boolean | ✅ | false | Revocation status |
| `revoked_at` | datetime \| null | ❌ | null | Revocation timestamp |

**Indexes**:

```javascript
// Query by user
db.refresh_tokens.createIndex({ "user_id": 1, "revoked": 1, "expires_at": -1 })

// Query by token hash (for validation)
db.refresh_tokens.createIndex({ "token_hash": 1 })

// TTL index (automatic cleanup)
db.refresh_tokens.createIndex(
  { "expires_at": 1 },
  { expireAfterSeconds: 0, name: "ttl_expires_at" }
)
```

**Notes**:
- **Security**: Only SHA-256 hash stored, not plaintext token
- **TTL**: Cosmos DB automatically deletes expired tokens
- **Revocation**: Supports manual token invalidation

---

### 6. `feedback` Collection

**Purpose**: User feedback and feature requests with voting system.

**Pydantic Model**: `backend/src/models/feedback.py::FeedbackItem`

**Schema**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `feedback_id` | string | ✅ | auto-generated | Unique feedback ID (`fb_<uuid>`) |
| `user_id` | string | ✅ | - | Submitter user ID (foreign key) |
| `title` | string | ✅ | - | Feedback title (max 100 chars) |
| `description` | string | ✅ | - | Detailed description (max 2000 chars) |
| `category` | enum | ✅ | - | Category: "bug", "feature", "improvement", "question" |
| `status` | enum | ✅ | "open" | Status: "open", "in_progress", "completed", "closed" |
| `votes` | integer | ✅ | 0 | Total upvotes count |
| `created_at` | datetime | ✅ | current UTC | Submission timestamp |
| `updated_at` | datetime | ✅ | current UTC | Last update timestamp |
| `completed_at` | datetime \| null | ❌ | null | Completion timestamp |
| `comments` | array[Comment] | ✅ | [] | Nested comments (embedded) |

**Comment Schema** (embedded):

```typescript
{
  comment_id: string,              // Unique comment ID
  user_id: string,                 // Commenter user ID
  content: string,                 // Comment text
  created_at: datetime,            // Comment timestamp
  is_admin: boolean                // Admin comment flag
}
```

**Indexes**:

```javascript
// Query by status and category
db.feedback.createIndex({ "status": 1, "category": 1, "votes": -1 })

// Query user's feedback
db.feedback.createIndex({ "user_id": 1, "created_at": -1 })
```

**Notes**:
- **Voting**: Users can vote once per item (tracked in `users.feedbackVotes`)
- **Comments**: Embedded as sub-documents (not separate collection)
- **Admin responses**: Marked with `is_admin` flag

---

## Data Relationships

```
users (1) ──< (N) chats
  │
  ├──< (N) messages
  │
  ├──< (N) credit_transactions
  │
  ├──< (N) refresh_tokens
  │
  └──< (N) feedback

chats (1) ──< (N) messages

credit_transactions (1) ─── (1) messages (optional link)
```

**Foreign Key Relationships** (enforced at application level):

| Parent Collection | Child Collection | Foreign Key Field |
|-------------------|------------------|-------------------|
| `users` | `chats` | `user_id` |
| `users` | `messages` | N/A (via chats) |
| `users` | `credit_transactions` | `user_id` |
| `users` | `refresh_tokens` | `user_id` |
| `users` | `feedback` | `user_id` |
| `chats` | `messages` | `chat_id` |
| `messages` | `credit_transactions` | `message_id` (optional) |

**Note**: MongoDB does not enforce referential integrity. Application code must maintain consistency.

---

## Cosmos DB Specific Considerations

### Sorting Limitations

**Problem**: Cosmos DB MongoDB API does NOT support sorting by `_id` when using compound filter queries.

**Example that FAILS**:
```javascript
db.chats.find({ user_id: "...", is_archived: false }).sort({ _id: -1 })
// Error: "The index path corresponding to the specified order-by item is excluded"
```

**Solution**: Use explicit timestamp fields:
```javascript
db.chats.find({ user_id: "...", is_archived: false }).sort({ updated_at: -1 })
```

**Reference**: See [Cosmos DB MongoDB Compatibility Guide](../deployment/cosmos-db-mongodb-compatibility.md)

### Indexing Requirements

**Compound Indexes**: Must include ALL filter fields + sort field (in order):

```javascript
// For query: find({ user_id, is_archived }).sort({ updated_at: -1 })
// Required index:
db.chats.createIndex({ user_id: 1, is_archived: 1, updated_at: -1 })
```

### Throughput Considerations

**Current Configuration**: 400 RU/s shared database throughput

**Query Costs** (approximate):
- Simple read by ID: 1-2 RU
- Indexed query: 2-5 RU
- Unindexed query: 10-100+ RU
- Large result sets: Higher cost

**Optimization**:
- Use projection to fetch only needed fields
- Create indexes for all frequent queries
- Monitor RU consumption in Azure Portal

**Reference**: See [MongoDB Cosmos DB Troubleshooting](../troubleshooting/mongodb-cosmos-db.md)

---

## Schema Evolution

### Version History

| Version | Changes | Migration Required |
|---------|---------|-------------------|
| **v0.5.3** | Added credit system fields to `users`, created `credit_transactions` | ✅ Yes - backfill credits |
| **v0.5.4** | Added `model` selection to `messages` metadata | ❌ No - optional field |
| **v0.5.5** | Changed `chats` sorting from `_id` to `updated_at` | ✅ Yes - index update |

### Migration Scripts

Migrations are manual (no automated migration system).

**Location**: Ad-hoc scripts in `scripts/` or via `mongosh` commands documented in version release notes.

**Example** (v0.5.5 Cosmos DB index update):
```bash
az cosmosdb mongodb collection update \
  --account-name financialagent-mongodb \
  --database-name _test \
  --name chats \
  --resource-group FinancialAgent \
  --idx '[
    {"key": {"keys": ["_id"]}},
    {"key": {"keys": ["user_id", "is_archived", "updated_at"]}}
  ]'
```

---

## Backup and Recovery

### Backup Strategy

**Azure Cosmos DB Automatic Backups**:
- **Frequency**: Continuous (every 4 hours)
- **Retention**: 30 days
- **Type**: Full backup
- **Recovery**: Point-in-time restore (contact Azure support)

**Manual Export** (for migration/testing):
```bash
# Export collection to JSON
mongosh "$MONGODB_URL" --eval "
  db.users.find().forEach(function(doc) {
    printjson(doc);
  })
" > users_export.json
```

### Disaster Recovery

**Recovery Time Objective (RTO)**: ~2 hours
**Recovery Point Objective (RPO)**: Up to 4 hours (backup frequency)

**Recovery Procedure**:
1. Contact Azure Support for point-in-time restore
2. Specify database name and target timestamp
3. Azure creates new Cosmos DB instance with restored data
4. Update connection string in Key Vault
5. Force-sync External Secrets
6. Restart application pods

**Reference**: See [Deployment Workflow](../deployment/workflow.md#rollback-procedure)

---

## Related Documentation

- **Pydantic Models**: `backend/src/models/`
- **Repository Layer**: `backend/src/database/repositories/`
- **Cosmos DB Compatibility**: [docs/deployment/cosmos-db-mongodb-compatibility.md](../deployment/cosmos-db-mongodb-compatibility.md)
- **Troubleshooting**: [docs/troubleshooting/mongodb-cosmos-db.md](../troubleshooting/mongodb-cosmos-db.md)
- **Credit System**: [docs/features/token-credit-economy.md](../features/token-credit-economy.md)
