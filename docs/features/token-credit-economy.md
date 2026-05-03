# Feature Specification: Token-Based Credit Economy

**Status**: Planning
**Priority**: High
**Target Version**: v0.6.0
**Created**: 2025-01-13
**Author**: System Architecture Team

---

## Executive Summary

Implement a token-based credit economy where users pay for AI operations based on actual token consumption. This creates a fair, transparent billing system with ~84% gross margin while providing detailed transaction tracking for support and refunds.

**Key Metrics**:
- **Currency Conversion**: 1元 = 100 Credits
- **Work Conversion**: 1 Credit = 200 Tokens
- **Target Margin**: ~84% gross profit
- **New User Grant**: 1,000 free credits (~10-15 AI conversations)

---

## Context & Problem Statement

### Current State
- ✅ LLM integration working (Alibaba DashScope Qwen-plus)
- ✅ Token usage logged but not persisted
- ✅ User authentication with JWT
- ❌ **No billing system** - unlimited free usage
- ❌ **No cost tracking** - can't calculate expenses
- ❌ **No usage limits** - potential for abuse

### Business Problem
1. **Unsustainable**: Free unlimited AI usage is not viable long-term
2. **No Transparency**: Users don't know what they're consuming
3. **No Revenue**: Cannot monetize premium AI features
4. **Resource Risk**: No protection against abuse or runaway costs

### User Problem
Users need:
- Fair pricing based on actual usage (not flat subscription)
- Transparency on what each request costs
- History of their spending
- Protection from unexpected charges

---

## Proposed Solution

### Economic Model

**Two-Tier Conversion System**:

```
User Money ──→ Credits ──→ AI Work
   1元          100        20,000 tokens
```

**Pricing Examples**:
| Scenario | Input Tokens | Output Tokens | Total | Credits | Cost (元) |
|----------|-------------|---------------|-------|---------|----------|
| Simple query | 100 | 150 | 250 | 1.25 | ¥0.0125 |
| Complex analysis | 500 | 2,000 | 2,500 | 12.5 | ¥0.125 |
| Long conversation | 1,000 | 3,500 | 4,500 | 22.5 | ¥0.225 |

**Free Tier**: New users get 1,000 credits (≈ 200,000 tokens ≈ 10-15 conversations)

### Architecture: Stateful API with Reconciliation

We use a **Stateful API Pattern** where the API endpoint handles:
1. Real-time streaming (user experience)
2. Immediate transaction creation (safety net)
3. Atomic credit deduction (revenue protection)

A lightweight **Reconciliation Worker** handles edge cases (server crashes, network failures).

---

## Technical Design

### System Architecture

**Request Flow** (`POST /api/chat/stream-v2`):

1. **Credit Check**: Verify `user.credits >= MIN_THRESHOLD (10)` → 402 if insufficient
2. **Create PENDING Transaction**: Generate `transaction_id`, insert with estimated_cost
3. **Stream LLM Response**: Call DashScope, stream via SSE, capture token usage
4. **Save Message**: Link to transaction_id for audit trail
5. **ACID Deduction**: MongoDB transaction → calculate cost, deduct credits, complete transaction

**Key Points**:
- Backend does NOT send balance back (frontend uses optimistic updates)
- Transaction record ensures we never lose a billable request

### Reconciliation Worker (Failure Safety Net)

**Purpose**: Handle rare cases where server crashes after streaming but before billing

**Trigger**: Kubernetes CronJob every 10 minutes

**Logic**:
```python
def reconcile_stuck_transactions():
    # Find transactions stuck in PENDING for >10 minutes
    stuck = transactions.find({
        "status": "PENDING",
        "created_at": {"$lt": now() - timedelta(minutes=10)}
    })

    for txn in stuck:
        # Check if user was actually served
        message = messages.find_one({
            "metadata.transaction_id": txn.transaction_id
        })

        if message:
            # User got response but wasn't billed - complete now
            complete_transaction(txn.transaction_id, message.metadata.tokens)
            logger.warning("Reconciled stuck transaction", txn_id=txn.transaction_id)
        else:
            # No response found - mark as FAILED (no charge)
            fail_transaction(txn.transaction_id)
            logger.info("Failed incomplete transaction", txn_id=txn.transaction_id)
```

**Deployment**:
- Local Dev: Python scheduler runs every 5 minutes (for testing)
- Test/Prod: Kubernetes CronJob with image: `backend:test-v0.6.0`

---

## Database Schema

### 1. Users Collection (Modified)

**Changes**: Add credit balance field

```python
class User(BaseModel):
    user_id: str
    email: str | None
    username: str
    # ... existing fields ...

    # NEW FIELDS
    credits: float = 1000.0  # Free credits on signup
    total_tokens_used: int = 0  # Lifetime usage (analytics)
    total_credits_spent: float = 0.0  # Lifetime spending
```

**Indexes**:
- Existing: `_id` (default)
- Recommended: `email`, `username` (for lookups)

---

### 2. Transactions Collection (New)

**Purpose**: Immutable audit trail for all credit operations

```python
class CreditTransaction(BaseModel):
    transaction_id: str  # Format: "txn_{uuid4()}"
    user_id: str
    chat_id: str
    message_id: str | None  # Links to assistant message

    # Status tracking
    status: Literal["PENDING", "COMPLETED", "FAILED"]

    # Cost details
    estimated_cost: float  # Conservative estimate at start
    actual_tokens: int | None  # Actual input + output tokens
    actual_cost: float | None  # Exact cost: actual_tokens / 200

    # Timestamps
    created_at: datetime
    completed_at: datetime | None

    # Metadata
    model: str = "qwen-plus"
    request_type: str = "chat"  # "chat", "analysis", etc.
```

**Indexes**:
- `transaction_id` (unique)
- `user_id` (for user history)
- `(status, created_at)` compound (for reconciliation queries)
- `chat_id` (for chat-level analytics)

**Retention**: Keep forever (legal/accounting requirement)

---

### 3. Messages Collection (Modified)

**Changes**: Add transaction link to metadata

```python
class MessageMetadata(BaseModel):
    # ... existing fields ...

    # NEW FIELDS
    transaction_id: str | None  # Links to credit transaction
    tokens_used: int | None  # Quick reference (also in transaction)
```

---

## API Endpoints

### 1. Modified Endpoints

#### `POST /api/chat/stream-v2` (Modified)

**Changes**:
- Add credit check before LLM call
- Create transaction record
- Deduct credits after streaming (server-side only)
- No SSE event for credit balance (frontend uses optimistic updates)

**NO NEW SSE EVENTS**: Backend does NOT send credit balance back.
Frontend uses optimistic updates and periodic refetch to sync with backend truth.

**Error Responses**:
```json
// Insufficient credits
{
  "type": "error",
  "error": "Insufficient credits. Required: ~10, Available: 5.2",
  "error_code": "INSUFFICIENT_CREDITS"
}
```

---

### 2. New Endpoints

#### `GET /api/users/me`

**Purpose**: Get current user profile including credit balance

**Response**:
```json
{
  "user_id": "user_abc",
  "username": "alice",
  "email": "alice@example.com",
  "credits": 987.5,
  "total_tokens_used": 12500,
  "total_credits_spent": 62.5,
  "created_at": "2025-01-01T00:00:00Z"
}
```

**Auth**: Required (JWT)

---

#### `GET /api/credits/transactions`

**Purpose**: Get user's credit transaction history

**Query Params**:
- `page` (default: 1)
- `page_size` (default: 20, max: 100)
- `status` (optional: filter by PENDING/COMPLETED/FAILED)

**Response**:
```json
{
  "transactions": [
    {
      "transaction_id": "txn_abc123",
      "chat_id": "chat_xyz",
      "status": "COMPLETED",
      "actual_tokens": 1700,
      "actual_cost": 8.5,
      "created_at": "2025-01-13T10:30:00Z",
      "completed_at": "2025-01-13T10:30:15Z"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 45,
    "total_pages": 3
  }
}
```

**Auth**: Required (JWT)

---

#### `POST /api/credits/purchase` (Placeholder)

**Purpose**: Purchase credits (future payment integration)

**Request**:
```json
{
  "amount": 5000,  // Credits to purchase
  "payment_method": "alipay"  // "alipay", "wechat", "card"
}
```

**Status**: Not implemented in v0.6.0 (return 501 Not Implemented)

---

#### `POST /api/admin/credits/adjust` (Admin Only)

**Purpose**: Manually adjust user credits (refunds, corrections)

**Request**:
```json
{
  "user_id": "user_abc",
  "amount": 50.0,  // Positive = add, negative = deduct
  "reason": "Refund for system error on 2025-01-13"
}
```

**Auth**: Admin required (`require_admin` dependency)

---

## Frontend Changes

### Components

1. **CreditBalance** (`App.tsx` header): Balance display with color coding (green >100, yellow 10-100, red <10)
2. **Cost Indicator** (chat input): Show "Estimated cost: ~5-10 credits"
3. **Transaction History** (`/credits/history`): Paginated list with filters

### State Management (Optimistic Updates)

**Hook**: `useUserProfile()` - Query with 30s staleTime, refetch on window focus

**Pattern**: Optimistically deduct on `onMutate`, rollback on error, invalidate on success

```typescript
// Cost estimation: baseTokens(300) + messageTokens(length/4) + outputEstimate(500)
const estimatedCost = Math.ceil(totalTokens / 200);
```

**Benefits**: Instant UI feedback, backend simplicity, eventual consistency

---

## Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| **Insufficient Credits** | Return 402, show purchase suggestion |
| **Estimate vs Actual Differs** | Allow once (goodwill), block next if < threshold |
| **Stream Cancellation** | Complete transaction with actual tokens used |
| **LLM Provider Error** | Mark FAILED, don't deduct credits |
| **Missing Token Count** | Fallback to tiktoken, round up conservatively |
| **Concurrent Requests** | MongoDB atomic transactions, optimistic locking |
| **Reconciliation Race** | Atomic update with status condition (PENDING only) |

---

## Testing Strategy

**Unit Tests**: CreditService (cost calc, balance check, atomic deduction), TransactionRepository (CRUD, reconciliation queries)

**Integration Tests**: Full chat flow, 402 rejection, concurrent requests, stream cancellation

**Manual Checklist**:
- [ ] New user gets 1000 credits
- [ ] Send message deducts correctly
- [ ] Transaction history shows records
- [ ] Reconciliation worker completes stuck transactions
- [ ] Admin can adjust credits

---

## Rollout Plan

| Phase | Changes | Deployment | Risk |
|-------|---------|------------|------|
| **Alpha** | Schema, CreditService, repos | Test env | Low |
| **Beta** | Credit endpoints, frontend display | Test env (5-10 users) | Medium |
| **v0.6.0** | Reconciliation worker, CronJob | Test → Prod | Medium |

---

## Monitoring & Observability

**Business Metrics**: Credits purchased/spent, avg cost per conversation, conversion rate

**Technical Metrics**: Transaction completion rate, failure rate, reconciliation corrections

**Alerts**: Failure rate >1%, reconciliation >10/hr, negative balance

**Logging**: Structured logs for transaction creation, credit deduction, reconciliation, errors

---

## Security Considerations

| Risk | Mitigation |
|------|------------|
| Credit injection | All operations server-side, admin audit logs |
| Token manipulation | Trust DashScope API, fallback to tiktoken |
| Transaction replay | Unique IDs, idempotent updates |
| Race conditions | MongoDB atomic transactions, reconciliation |

---

## Decisions Made

1. **Negative Balance**: Option B - Allow one goodwill negative, then block
2. **Payment Providers**: Alipay + WeChat Pay (v0.7.0)
3. **Free Credits**: One-time 1000 credits
4. **Admin Limits**: Max 1000 credits per adjustment with audit logging

---

## Success Criteria

**Business**: 80%+ users above 0 credits, <5% billing tickets, ≥75% margin

**Technical**: Zero double-charging, 99.9% completion rate, <100ms latency added

**UX**: Clear cost understanding, no surprise errors, 30%+ use transaction history

---

## Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Double charging | ACID transactions + reconciliation audit |
| Credit loss | Reconciliation worker + alerts |
| Token counting errors | Fallback to tiktoken + logging |
| Race conditions | MongoDB transactions + testing |

---

## Future Enhancements

- **v0.7.0**: Alipay/WeChat Pay integration, invoice generation
- **v0.8.0**: Credit packages, subscriptions, referrals
- **v0.9.0**: Cost prediction, usage dashboard, budget alerts

---

## References

- [System Design](../architecture/system-design.md)
- [Alibaba DashScope Pricing](https://help.aliyun.com/zh/dashscope/developer-reference/tongyi-thousand-questions-metering-and-billing)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)

---

## File Structure

**Backend**: `models/transaction.py`, `services/credit_service.py`, `api/credits.py`, `scripts/reconciliation_worker.py`

**Frontend**: `components/CreditBalance.tsx`, `hooks/useUserProfile.ts`

**K8s**: `cronjob-reconciliation.yaml`

---

## Cost Examples

| Scenario | Tokens | Credits | Cost (元) |
|----------|--------|---------|----------|
| Simple query | 150 | 0.75 | ¥0.0075 |
| Technical analysis | 2,500 | 12.5 | ¥0.125 |
| 10-message conversation | 8,000 | 40 | ¥0.40 |

**Free Credits**: 1000 = ~10-15 conversations (2-3 weeks casual usage)
