# Feature Specifications

This directory contains detailed specifications for all new features before implementation.

## Purpose

Feature specs ensure:

- Clear understanding of requirements before coding
- Alignment between stakeholders and developers
- Design decisions are documented
- Implementation scope is well-defined
- Acceptance criteria are established upfront

## When to Create a Feature Spec

Create a feature spec for:

- ✅ New user-facing features
- ✅ Significant architectural changes
- ✅ New API endpoints or data models
- ✅ Complex business logic
- ✅ Third-party integrations

Skip feature specs for:

- ❌ Bug fixes (use troubleshooting docs instead)
- ❌ Minor refactoring
- ❌ Documentation updates
- ❌ Dependency upgrades

## Feature Spec Template

````markdown
# Feature: [Feature Name]

> **Status**: [Draft | Under Review | Approved | Implemented]
> **Created**: YYYY-MM-DD
> **Last Updated**: YYYY-MM-DD
> **Owner**: [Your Name]

## Context

Why is this feature needed? What user problem does it solve?

**User Story**:
As a [user type], I want to [action], so that [benefit].

**Background**:

- Current situation and limitations
- Business/user impact
- Related features or dependencies

## Problem Statement

Clear, concise description of the problem to solve.

**Current Pain Points**:

1. [Pain point 1]
2. [Pain point 2]

**Success Metrics**:

- How will we measure success?
- What KPIs or user metrics should improve?

## Proposed Solution

### High-Level Approach

Describe the technical approach at a conceptual level.

### Architecture Changes

**New Components**:

- Component 1: Purpose and responsibilities
- Component 2: Purpose and responsibilities

**Modified Components**:

- Existing component: What changes and why

**Data Models**:

```python
# Example Pydantic model
class NewFeature(BaseModel):
    id: str
    name: str
    created_at: datetime
```
````

**API Endpoints**:

```
POST   /api/feature          Create new feature
GET    /api/feature/{id}     Get feature by ID
PUT    /api/feature/{id}     Update feature
DELETE /api/feature/{id}     Delete feature
```

### UI/UX Changes

**New Screens/Components**:

- Screen 1: Description, mockup or wireframe
- Component 1: Purpose and behavior

**User Flow**:

1. User navigates to...
2. User clicks...
3. System responds with...

### Technical Implementation Details

**Frontend**:

- React components to create/modify
- State management approach
- API integration points

**Backend**:

- New routes/endpoints
- Database schema changes
- External API integrations

**Database**:

- New collections/tables
- Indexes required
- Migration strategy

## Implementation Plan

### Phase 1: Foundation

- [ ] Task 1: Description
- [ ] Task 2: Description

### Phase 2: Core Feature

- [ ] Task 3: Description
- [ ] Task 4: Description

### Phase 3: Polish & Testing

- [ ] Task 5: Description
- [ ] Task 6: Description

**Estimated Effort**: [X days/weeks]

## Acceptance Criteria

Feature is complete when:

- [ ] **Functional Requirements**:
  - [ ] Criterion 1
  - [ ] Criterion 2

- [ ] **Technical Requirements**:
  - [ ] All tests passing
  - [ ] Code reviewed and approved
  - [ ] Documentation updated

- [ ] **User Experience**:
  - [ ] UI matches design specs
  - [ ] Error handling is user-friendly
  - [ ] Performance meets targets (e.g., <200ms response time)

## Testing Strategy

**Unit Tests**:

- Test A: What it validates
- Test B: What it validates

**Integration Tests**:

- Test C: End-to-end flow
- Test D: External API integration

**Manual Testing**:

1. Test scenario 1
2. Test scenario 2

## Security Considerations

- Authentication/authorization requirements
- Data validation rules
- Sensitive data handling
- Rate limiting needs

## Performance Considerations

- Expected load (requests/second, concurrent users)
- Database query optimization
- Caching strategy
- Resource limits

## Rollout Strategy

**Development**:

- Feature flag: `enable_feature_x`
- Test with internal users first

**Production**:

- Phased rollout (10% → 50% → 100%)
- Monitoring metrics during rollout
- Rollback plan if issues detected

## Open Questions

1. Question 1?
   - Options: A, B, C
   - Decision: TBD

2. Question 2?
   - Options: X, Y
   - Decision: TBD

## Dependencies

- Dependency 1: Why needed, current status
- Dependency 2: Why needed, current status

## Risks and Mitigations

| Risk   | Impact | Probability | Mitigation          |
| ------ | ------ | ----------- | ------------------- |
| Risk 1 | High   | Medium      | Mitigation strategy |
| Risk 2 | Low    | High        | Mitigation strategy |

## References

- Related docs: [Link to architecture doc]
- Related features: [Link to related spec]
- Design mockups: [Link to Figma/etc]
- External resources: [Link to research/docs]

---

## Change Log

- **YYYY-MM-DD**: Initial draft
- **YYYY-MM-DD**: Updated based on review feedback
- **YYYY-MM-DD**: Approved and implementation started

```

## Completed Feature Specs

Browse existing feature specs in this directory for examples:

### Active Hardening Program

- **[Project Hardening Program](project-hardening-program.md)** — parallel work packages, merge order, and shared completion rules
- **[PH-001 Local Network Perimeter](project-hardening-local-network-perimeter.md)** — bind the local stack to loopback and prove connectivity
- **[PH-002 Insights Prefetch Contract](project-hardening-insights-prefetch-contract.md)** — repair and test the Insights/DataManager shared-data boundary
- **[PH-003 Backend Type Safety](project-hardening-backend-type-safety.md)** — converge strict mypy and runtime domain contracts
- **[PH-004 CI Agent Quality Gates](project-hardening-ci-agent-quality-gates.md)** — enforce eval, typing, security, and browser smoke in PR CI
- **[PH-005 Untrusted Markdown Safety](project-hardening-markdown-safety.md)** — sanitize the LLM-to-browser rendering boundary
- **[PH-006 Frontend Type and Lint Quality](project-hardening-frontend-quality.md)** — validate API/SSE input and restore lint signal
- **[PH-007 Agent Orchestration Coverage](project-hardening-agent-orchestration-coverage.md)** — test real internal workflow composition and persistence invariants
- **[PH-008 Reproducible Runtime Builds](project-hardening-reproducible-builds.md)** — lock dependencies and validate non-root clean builds
- **[PH-009 Source Decomposition](project-hardening-source-decomposition.md)** — split oversized production modules after functional hardening
- **[PH-010 Version Metadata](project-hardening-version-metadata.md)** — unify package, runtime, UI, and documentation versions

### Architecture & Refactoring
- **[Portfolio Agent Architecture](portfolio-agent-architecture-refactor.md)** — 3-phase analysis (research → decisions → execution)

### AI & Agent System
- **[Automatic Chat Flow Routing](automatic-chat-flow-routing.md)** — rule-first routing with a lightweight classifier fallback
- **[Chat Symbol Context](chat-symbol-context.md)** — inject the active UI symbol into chat context so the agent does not have to re-ask
- **[Deep Agent Symbol Clarification](deep-agent-symbol-clarification.md)** — remove silent ticker fallback and require confirmation for ambiguous research requests
- **[Mongo-Authoritative Conversation State](mongo-authoritative-conversation-state.md)** — make persisted Mongo history the only cross-turn state source and remove decorative MemorySaver semantics
- **[Deep Research Conversation Context](deep-research-conversation-context.md)** — carry prior thesis, horizon, risk tolerance, and constraints into follow-up Deep Research
- **[Watchlist Analysis Persistence Wiring](watchlist-persistence-wiring.md)** — update the real watchlist row and refresh its analysis timestamp after per-symbol analysis
- **[Agent Task Cancellation](agent-task-cancellation.md)** — propagate browser Stop through SSE handlers into active model, tool, and research tasks
- **[Honest Streaming Semantics](honest-streaming-semantics.md)** — distinguish real model-token streaming from buffered ReAct and Deep final responses
- **[Shared Durable Run Model](shared-run-model.md)** — persist one execution status and observability contract across chat and Portfolio flows
- **[Unified Chat Handler Lifecycle](unified-chat-handler-lifecycle.md)** — centralize chat setup, context, terminal persistence, title handling, clarification, and cancellation across Direct, ReAct, and Deep
- **[Standard Agent Event Envelope](standard-agent-event-envelope.md)** — wrap every agent SSE event with one run ID, monotonic sequence, canonical type, timestamp, and typed payload
- **[Request Idempotency](request-idempotency.md)** — atomically reuse one durable run and terminal message for duplicate client request IDs
- **[Agent Evaluation Framework](agent-evaluation-framework.md)** — run versioned bilingual golden cases with deterministic router and symbol-safety quality gates
- **[Prompt Registry Foundation](prompt-registry-foundation.md)** — version the router prompt and replace free-text JSON parsing with Pydantic structured output
- **[Runtime-Linked Prompt Migrations](runtime-linked-prompt-migrations.md)** — route Direct/ReAct and symbol extraction through deterministic registry templates with request-local usage metadata
- **[Deep Prompt Governance](deep-prompt-governance.md)** — migrate debate, rebuttal, and verdict prompts while recording conditional usage on every terminal path
- **[Consistency Gate Prompt Governance](consistency-gate-prompt-governance.md)** — registry-version the structured research-quality gate only when its LLM call executes
- **[Portfolio Phase 2 Prompt Governance](portfolio-phase2-prompt-governance.md)** — preserve the complete decision contract behind a versioned renderer with successful-call usage metadata
- **[Prompt Governance Browser Evidence](prompt-governance-e2e.md)** — verify governed chat prompts and Portfolio background lifecycle through real browser interactions
- **[Deep Structured Decisions](deep-structured-decisions.md)** — replace regex-parsed debate decisions with strict Pydantic outputs while preserving Markdown verdicts
- **[Write-Time Translation](write-time-translation.md)** — translate LLM output to `zh-CN` on the write path so the read path skips `/api/translate`

### Market Data & Visualization
- **[Market Insights Trend Visualization](market-insights-trend-visualization.md)** — sparklines + expanded trend charts for the daily insights snapshot
- **[Extended-Hours Trading Data](extended-hours-trading-data.md)** — pre-market / after-hours session badges + quote routing
- **[Symbol Search & Chart Improvements](symbol-search-and-chart-improvements.md)** — deduplication, OHLC tooltips, custom date ranges
- **[Fibonacci Trend Detection Improvements](fibonacci-trend-detection-improvements.md)** — adaptive swing lookback + direction labeling

> **Index parity rule**: every `*.md` in this directory (except `README.md`)
> must appear in the list above with `status: shipped | in-progress |
> planning`. Do not list specs that have been deleted.

## Workflow

1. **Create Draft**: Copy template above, fill in details
2. **Discussion**: Review with team, gather feedback
3. **Approval**: Get sign-off before implementation
4. **Implementation**: Reference spec during development
5. **Update**: Keep spec updated if design changes
6. **Archive**: Mark as "Implemented" when complete

## Tips

- **Be specific**: Vague specs lead to rework
- **Include examples**: Code snippets, mockups, user flows
- **Think through edge cases**: What happens when...?
- **Consider non-functional requirements**: Performance, security, scalability
- **Link to related docs**: Don't duplicate, reference existing documentation
```
