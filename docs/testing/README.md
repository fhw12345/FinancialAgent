# Testing Documentation

This directory contains comprehensive testing documentation for the Financial Agent application.

---

## 📁 Documentation Structure

### 1. [E2E Automation Guide](./e2e-automation-guide.md)
**Purpose**: Complete E2E testing procedures for Playwright automation

**Use this when**:
- Running automated E2E tests with Playwright
- Debugging test failures
- Setting up new E2E test scenarios
- Understanding critical configuration (viewport, selectors, etc.)

**Contains**:
- Quick start instructions
- Critical configuration requirements (viewport 2000px, no zoom)
- All 4 test workflows with proven selectors:
  - Test 1: Login & Authentication
  - Test 2: Chat/Platform Analysis
  - Test 3: Portfolio Dashboard
  - Test 4: Watchlist Management
- Troubleshooting guide (chat input, Send button, cooldown handling)
- Lessons learned from debugging sessions

**Status**: ✅ All 4 tests passing (100% success rate)

---

### 2. [E2E Reference](./e2e-reference.md)
**Purpose**: Comprehensive API endpoints, UI selectors, and workflow reference

**Use this when**:
- Looking up API endpoint details
- Finding correct Playwright selectors
- Understanding user workflows
- Writing new E2E tests

**Contains**:
- Login credentials (admin/<password>)
- All 35+ backend API endpoints with descriptions
- 6 detailed user workflows (Login, Chat, Portfolio, Feedback, Transactions, Health)
- 60+ Playwright selectors organized by page
- Technical details (authentication, database, hooks)

**Status**: Complete reference documentation

---

### 3. [Testing Strategy](../development/testing-strategy.md)
**Purpose**: Unit and integration test coverage strategy

**Use this when**:
- Planning unit test coverage improvements
- Understanding current test coverage gaps
- Writing pytest or vitest tests
- Reviewing testing best practices

**Contains**:
- Current coverage baseline (Backend 43%, Frontend <5%)
- Coverage goals by layer (Security, Infrastructure, Business Logic, etc.)
- Test execution plan (Phase 1-4)
- Testing best practices (pytest, Vitest, React Testing Library)
- Running tests instructions

**Status**: Strategic planning document (updated 2025-10-25)

---

## 🚀 Quick Links

### Running Tests

**E2E Tests** (Playwright):
```bash
cd /tmp/webtesting/financial-agent-full
source venv/bin/activate
python test_full_application.py
```

**Backend Unit Tests** (pytest):
```bash
cd backend
make test              # Run all tests
make test-cov          # With coverage report
```

**Frontend Tests** (Vitest - must run in Docker):
```bash
docker compose exec frontend npm test
docker compose exec frontend npm run test:coverage
```

### Documentation Hierarchy

```
docs/
├── testing/
│   ├── README.md                      ← You are here
│   ├── e2e-automation-guide.md        ← Playwright procedures (how-to)
│   └── e2e-reference.md               ← API/selector reference (what)
└── development/
    ├── testing-strategy.md            ← Unit test coverage strategy
    ├── coding-standards.md            ← Code patterns & debugging
    └── verification.md                ← Validation procedures
```

---

## 📋 Test Status Summary

| Test Type | Coverage | Status | Documentation |
|-----------|----------|--------|---------------|
| **E2E Tests** | 4/4 passing (100%) | ✅ | e2e-automation-guide.md |
| **Backend Unit Tests** | 43% (205 tests) | 🟡 | testing-strategy.md |
| **Frontend Tests** | <5% (11 tests) | 🔴 | testing-strategy.md |

**Last Updated**: 2025-11-10
