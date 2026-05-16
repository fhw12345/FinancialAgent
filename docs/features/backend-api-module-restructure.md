---
title: Backend API Module Restructure
status: shipped
version: backend@0.8.8
last_updated: 2025-12-14
owner: maintainer
related_paths:
  - backend/src/api/
  - backend/src/agent/
  - backend/src/services/
---

# Backend API Module Restructure

## Overview

Major refactoring of the backend codebase from monolithic single-file modules to a modular package structure. This improves maintainability, testability, and code organization while enforcing the 500-line file limit.

## Problem Statement

Several backend files exceeded the 500-line limit and contained multiple responsibilities:
- `backend/src/api/analysis.py` - 1,415 lines
- `backend/src/api/chat.py` - 1,199 lines
- `backend/src/api/portfolio.py` - 892 lines
- `backend/src/api/feedback.py` - 648 lines

This made the codebase difficult to navigate, test, and maintain.

## Solution

Split large files into focused modules organized by domain responsibility.

### API Layer Restructure

**Before**: Single files in `backend/src/api/`
**After**: Package directories with focused modules

```
backend/src/api/
├── analysis/
│   ├── __init__.py      # Router exports
│   ├── fibonacci.py     # Fibonacci analysis endpoint
│   ├── technical.py     # Stochastic, market structure
│   ├── fundamentals.py  # Company fundamentals
│   ├── macro.py         # Macro sentiment (VIX, sectors)
│   ├── news.py          # News sentiment analysis
│   ├── history.py       # Analysis history endpoints
│   └── shared.py        # Common utilities
├── chat/
│   ├── __init__.py
│   ├── endpoints.py     # Chat CRUD operations
│   ├── helpers.py       # Message formatting, validation
│   └── streaming/
│       ├── react_agent.py    # ReAct agent streaming
│       └── simple_agent.py   # Simple agent streaming
├── feedback/
│   ├── __init__.py
│   ├── crud.py          # Feedback CRUD
│   ├── admin.py         # Admin operations
│   ├── comments.py      # Comment management
│   └── upload.py        # Image upload handling
├── market/
│   ├── __init__.py
│   ├── prices.py        # Price data endpoints
│   ├── search.py        # Symbol search
│   ├── fundamentals.py  # Market fundamentals
│   └── status.py        # Market status
└── portfolio/
    ├── __init__.py
    ├── holdings.py      # Holdings management
    ├── orders.py        # Order operations
    ├── transactions.py  # Transaction history
    ├── chats.py         # Portfolio chat history
    └── history.py       # Analysis history
```

### Agent Layer Restructure

**Portfolio Agent** (3-phase architecture):
```
backend/src/agent/portfolio/
├── __init__.py
├── agent.py             # Main orchestration
├── phase1_research.py   # Market research (concurrent)
├── phase2_decisions.py  # Investment decisions (single LLM call)
└── phase3_execution.py  # Trade execution (programmatic)
```

**Order Optimizer**:
```
backend/src/agent/optimizer/
├── __init__.py
├── base.py              # Types and interfaces
├── plan_builder.py      # Optimization plan generation
├── executor.py          # Plan execution
└── order_helpers.py     # Utility functions
```

**Alpha Vantage Tools**:
```
backend/src/agent/tools/alpha_vantage/
├── __init__.py
├── quotes.py            # Price and quote fetching
├── fundamentals.py      # Company fundamentals
├── technical.py         # Technical indicators
└── news.py              # News sentiment
```

### Services Layer Restructure

```
backend/src/services/
├── alpaca/
│   ├── base.py          # Shared client and config
│   ├── orders.py        # Order management
│   ├── positions.py     # Position tracking
│   ├── helpers.py       # Utility functions
│   └── service.py       # Main service facade
├── formatters/
│   ├── base.py          # Shared formatting utilities
│   ├── fundamentals.py  # Company data formatting
│   ├── market.py        # Market data formatting
│   └── technical.py     # Indicator formatting
└── watchlist/
    ├── analyzer.py      # Main analyzer class
    ├── analysis.py      # Analysis logic
    ├── chat_manager.py  # Chat session handling
    ├── context_handler.py # Context building
    └── order_handler.py # Order processing
```

### Shared Utilities Module

New centralized utilities:
```
backend/src/shared/
├── __init__.py          # Unified exports
├── formatters.py        # Number/currency/percentage formatting
└── sanitizers.py        # Input sanitization and validation
```

## Benefits

1. **Single Responsibility**: Each module has one clear purpose
2. **Testability**: Smaller modules are easier to unit test
3. **Navigation**: Developers can find code faster
4. **Maintainability**: Changes are isolated to specific modules
5. **Code Review**: Smaller files make PRs easier to review
6. **File Limits**: All files now under 500 lines

## Migration Notes

### Import Changes

Old imports:
```python
from src.api.analysis import router as analysis_router
from src.api.chat import router as chat_router
```

New imports (same public interface):
```python
from src.api.analysis import router as analysis_router  # From __init__.py
from src.api.chat import router as chat_router          # From __init__.py
```

The `__init__.py` files re-export routers, maintaining backward compatibility.

### Router Registration

No changes required in `main.py` - routers are exported from package `__init__.py` files.

## Testing

All 721 unit tests pass after restructuring:
```bash
cd backend && make test
# 721 tests passed
```

## Related Documentation

- [Portfolio Agent Architecture](portfolio-agent-architecture-refactor.md) - 3-phase analysis details
- [Coding Standards](../development/coding-standards.md) - File length limits
- [Agent Architecture](../architecture/agent-architecture.md) - Overall architecture

---

**Last Updated**: 2025-12-14
