# Feedback & Community Roadmap Platform

**Status**: ✅ **IMPLEMENTED** (Backend v0.5.2, Frontend v0.8.3) - Released 2025-10-12

**Test Environment URL**: http://localhost:3000/feedback (login required)

**Feature Specification and Implementation Plan**

---

## 1. Feature Overview

A self-contained system for collecting, prioritizing, and acting on user feedback directly within KlineMatrix. The platform enables authenticated users to submit feature requests and bug reports, vote on existing items, and engage in discussions through a transparent, data-driven roadmap.

**Key Goals:**
- Keep the entire feedback loop within our ecosystem
- Foster strong community engagement
- Provide AI-ready, machine-readable data
- Enable data-driven product decisions

---

## 2. Current Project Structure Analysis

**Backend**: FastAPI + Motor (MongoDB) + Pydantic, Repository pattern, JWT auth (get_current_user_id, require_admin)

**Frontend**: React 18 + TypeScript 5, TailwindCSS, React Query, react-markdown + remark-gfm

**Database**: Custom IDs (e.g., `chat_abc123`), async repositories

---

## 3. Technical Design Decisions

### 3.1 Vote Counting Strategy
**Problem**: Unbounded arrays in MongoDB cause performance degradation and eventually hit document size limits (16MB).

**Solution**: Atomic counters + separate user vote tracking
- `FeedbackItem.voteCount`: Number field, updated atomically (`$inc`)
- `User.feedbackVotes`: Array of voted item IDs (for UI state)
- **Performance**: O(1) vote count updates, no document size issues

### 3.2 Comments Architecture
**Problem**: Embedded comments create unbounded arrays in FeedbackItems.

**Solution**: Separate Comments collection
- Each comment is a document with `itemId` reference
- Indexed on `itemId` for fast retrieval
- Supports pagination and sorting
- No impact on FeedbackItem document size

### 3.3 Content Format
**Standard**: Markdown for all user-generated content
- **Why**: Portable, structured, LLM-friendly
- **Libraries**:
  - Backend: Store as plain text
  - Frontend: `react-markdown` + `remark-gfm`
- **Benefit**: AI agents can parse and analyze easily

### 3.4 AI Integration
**Design Principles**:
1. **API-First**: Primary interface for agents is structured JSON
2. **Type Field**: Enum (`feature` | `bug`) for agent decision-making
3. **Status Tracking**: Clear workflow states
4. **Export Endpoint**: Snapshot capability for batch processing

---

## 4. Database Schema

### 4.1 FeedbackItems Collection

**Fields**: `item_id`, `title`, `description` (Markdown), `authorId`, `type` (feature|bug), `status` (under_consideration|planned|in_progress|completed), `voteCount`, `commentCount`, `createdAt`, `updatedAt`

**Indexes**: `item_id` (unique), `type`, `voteCount` (desc), `createdAt`

### 4.2 Comments Collection

**Fields**: `comment_id`, `itemId` (reference), `authorId`, `content`, `createdAt`

**Indexes**: `comment_id` (unique), `itemId` (fast lookup), `createdAt`

### 4.3 Users Collection (Modification)

**Add field**: `feedbackVotes: string[]` - Array of voted item IDs for UI state

---

## 5. Backend Implementation Plan

### 5.1 Models (`feedback.py`)

**Types**: `FeedbackType = Literal["feature", "bug"]`, `FeedbackStatus = Literal["under_consideration", "planned", "in_progress", "completed"]`

**Request Models**:
- `FeedbackItemCreate`: title (5-200 chars), description (10-10000 chars), type
- `CommentCreate`: content (1-5000 chars)

**Response Models**:
- `FeedbackItem`: item_id, title, description, authorId, type, status, voteCount, commentCount, createdAt, updatedAt, hasVoted (computed)
- `Comment`: comment_id, itemId, authorId, content, createdAt, authorUsername (joined)

### 5.2 Repositories

**FeedbackRepository**: `create`, `get_by_id`, `list_by_type`, `increment_vote_count`, `increment_comment_count`, `get_all`

**CommentRepository**: `create`, `list_by_item`

**UserRepository (modified)**: `add_vote`, `remove_vote`, `get_user_votes`

### 5.3 Service Layer

**`backend/src/services/feedback_service.py`**
- **Purpose**: Orchestrate repositories, business logic
- **Methods**:
  - `create_item(item: FeedbackItemCreate, authorId: str) -> FeedbackItem`
  - `get_item(item_id: str, user_id: str | None) -> FeedbackItem`
    - Inject `hasVoted` field based on user's votes
  - `list_items(type: FeedbackType, user_id: str | None) -> list[FeedbackItem]`
    - Inject `hasVoted` for each item
  - `vote_item(item_id: str, user_id: str) -> bool`
    - Check if already voted (idempotent)
    - Increment vote count atomically
    - Add to user's feedbackVotes
  - `unvote_item(item_id: str, user_id: str) -> bool`
    - Decrement vote count
    - Remove from user's feedbackVotes
  - `add_comment(itemId: str, comment: CommentCreate, authorId: str) -> Comment`
    - Create comment
    - Increment commentCount on item
  - `get_comments(itemId: str) -> list[Comment]`
    - Join with users collection for author usernames
  - `export_all() -> str`  # Generate Markdown snapshot

### 5.4 API Endpoints (`api/feedback.py`)

**Router**: `/api/feedback`

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/items` | POST | Required | Create feedback item |
| `/items` | GET | Optional | List items (filter by type) |
| `/items/{item_id}` | GET | Optional | Get item details |
| `/items/{item_id}/vote` | POST | Required | Cast vote (204) |
| `/items/{item_id}/vote` | DELETE | Required | Remove vote (204) |
| `/items/{item_id}/comments` | POST | Required | Add comment |
| `/items/{item_id}/comments` | GET | Public | List comments |
| `/export` | GET | Required | Markdown snapshot |

**Note**: Create `get_current_user_id_optional` dependency for public endpoints.

---

## 6. Frontend Implementation Plan

### 6.1 Navigation Update (`App.tsx`)

Update `activeTab` type to include `"feedback"`, add button and route for `<FeedbackPage />`

### 6.2 Page & Components

**FeedbackPage.tsx**: PageHeader + SubmitButton + DualLeaderboards (features/bugs)

**FeedbackLeaderboard.tsx**: Props `type: "feature" | "bug"`, React Query fetch, vote counts, click → detail

**FeedbackListItem.tsx**: Title, status badge, vote/comment counts, optimistic voting

**FeedbackDetailPage.tsx**: Back button, header, Markdown description (react-markdown + remark-gfm), comment section/form

### 6.3 Forms

**SubmitFeedbackForm.tsx**: Modal with title, description, type radio (feature/bug)

**CommentForm.tsx**: Textarea + submit button

### 6.4 API Client (`feedbackApi.ts`)

Methods: `listItems(type?)`, `getItem(itemId)`, `createItem(data)`, `voteItem(itemId)`, `unvoteItem(itemId)`, `getComments(itemId)`, `addComment(itemId, content)`

---

## 7. Implementation Phases

### Phase 1: Backend Foundation (Day 1-2)
1. Create Pydantic models (`feedback.py`)
2. Create repositories (feedback, comment, user modifications)
3. Create service layer (`feedback_service.py`)
4. Create API endpoints (`api/feedback.py`)
5. Add dependency injection setup
6. Test all endpoints with curl/Postman

**Deliverable**: Fully functional backend API

### Phase 2: Frontend - Leaderboards (Day 3-4)
1. Update navigation in `App.tsx`
2. Create `FeedbackPage.tsx`
3. Create `FeedbackLeaderboard.tsx`
4. Create `FeedbackListItem.tsx`
5. Implement voting with optimistic updates
6. Create submit form modal

**Deliverable**: Working leaderboards with voting

### Phase 3: Frontend - Detail View (Day 5)
1. Add routing for detail view (or modal)
2. Create `FeedbackDetailPage.tsx`
3. Implement Markdown rendering
4. Create comment section
5. Create comment form

**Deliverable**: Complete feedback loop

### Phase 4: Polish & Testing (Day 6)
1. Add loading states and error handling
2. Improve UI/UX (animations, transitions)
3. Add empty states
4. Test voting race conditions
5. Test comment threading
6. Add export endpoint (admin only)

**Deliverable**: Production-ready feature

### Phase 5: AI Integration (Future)
1. Create AI agent client for feedback API
2. Implement auto-categorization (feature vs bug)
3. Implement sentiment analysis on comments
4. Auto-generate feature spec from high-voted items

---

## 8. File Structure

**Backend**: `models/feedback.py`, `repositories/feedback_repository.py`, `repositories/comment_repository.py`, `services/feedback_service.py`, `api/feedback.py`, `api/dependencies/feedback_deps.py`, `user_repository.py` (modify)

**Frontend**: `pages/FeedbackPage.tsx`, `pages/FeedbackDetailPage.tsx`, `components/feedback/` (Leaderboard, ListItem, SubmitForm, CommentSection, CommentForm), `services/feedbackApi.ts`, `App.tsx` (modify)

---

## 9. Testing Strategy

**Backend**: `test_create_feedback_item`, `test_vote_idempotency`, `test_atomic_vote_counting`, `test_comment_creation`, `test_markdown_export`

**Frontend**: Renders leaderboard correctly, handles optimistic voting, filters by type

---

## 10. Success Metrics

1. **Engagement**: % of active users who vote or comment
2. **Feedback Quality**: Average votes per item (indicates resonance)
3. **Response Time**: Time from submission to status update
4. **AI Readiness**: Export endpoint usage by automation tools
5. **Community Growth**: Month-over-month increase in submissions

---

## 11. Future Enhancements

1. **Notifications**: Email users when their item status changes
2. **Tags**: Add tags for categorization (e.g., #ui, #performance)
3. **Attachments**: Allow image uploads for bug reports
4. **Upvote Threshold**: Auto-promote items to "Planned" at 50 votes
5. **AI Auto-Response**: LLM generates initial response to new items
6. **GitHub Integration**: Auto-create GitHub issues from high-voted items

---

## 12. Open Questions

1. **Navigation**: Tab-based or separate route?
   - **Recommendation**: Tab-based (simpler, consistent with current app)

2. **Detail View**: Modal or dedicated page?
   - **Recommendation**: Dedicated page (better for sharing links)

3. **Vote Button**: Heart, thumbs up, or +1?
   - **Recommendation**: Thumbs up (universal, simple)

4. **Comment Threading**: Flat or nested?
   - **Recommendation**: Flat for MVP (simpler), nested later

5. **Export Format**: JSON or Markdown?
   - **Recommendation**: Markdown (more portable, LLM-friendly)

---

## 13. Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Vote count race conditions | High | Use atomic `$inc` operations |
| Unbounded comment arrays | High | Separate Comments collection |
| Spam submissions | Medium | Rate limiting per user |
| Inappropriate content | Medium | Admin moderation queue (future) |
| MongoDB document size limit | Low | Separate collections, no embedded arrays |

---

## 14. Dependencies

**Backend**:
- motor (already installed)
- structlog (already installed)
- fastapi (already installed)

**Frontend**:
- react-markdown (already installed)
- remark-gfm (already installed)
- @tanstack/react-query (already installed)

**No new dependencies required!**

---

## 15. Acceptance Criteria

### Must Have (MVP)
- [x] Authenticated users can submit feedback
- [x] Two separate leaderboards (features/bugs)
- [x] Vote/unvote functionality
- [x] Comment on feedback items
- [x] Markdown rendering for descriptions
- [x] API-first design for AI integration

### Nice to Have
- [ ] Real-time vote count updates (WebSocket)
- [ ] Markdown preview in forms
- [ ] Export endpoint for admin
- [ ] Comment edit/delete
- [ ] Status update history

---

## Implementation Ready ✅

This feature is fully specified and ready for implementation. All technical decisions are made, file structure is clear, and patterns match existing codebase conventions.
