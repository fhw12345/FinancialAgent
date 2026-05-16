---
title: Coding Standards and Best Practices
status: shipped
version: n/a
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/pyproject.toml
  - frontend/package.json
  - .pre-commit-config.yaml
---

# Coding Standards and Best Practices

## General Principles

### Code Quality
- **File Size Limit**: Maximum 500 lines per file - split into modules when exceeded
- **Documentation**: Descriptive docstrings at top of every file explaining purpose and context
- **Comments**: Rich comments required for all key business logic - explain "why", not "what"
- **No Duplication**: DRY principle - centralize shared logic in utils modules, avoid duplicate code

### Quality Gates
Before every commit, run:
```bash
make fmt && make test && make lint
```

All checks must pass before code can be committed.

## Python Standards

### Modern Syntax
- Use `|` for type unions: `str | None` instead of `Optional[str]`
- Use `match/case` for pattern matching
- Use f-strings for string formatting
- Use `@dataclass` for data classes

### Type Hints
Type hints are required for all functions and methods:

```python
def analyze_fibonacci(symbol: str, timeframe: str = "6mo") -> dict[str, Any]:
    """Analyze Fibonacci retracement levels."""
    pass
```

### Type Safety (v0.5.3+)

**Strict Type Checking**: All code must pass `mypy` with zero errors.

**Required Patterns**:
```python
# 1. Explicit return types for all functions
async def get_user(user_id: str) -> User | None:
    return await user_repo.get_by_id(user_id)

# 2. Type annotations on intermediate variables (prevent Any propagation)
count: int = await collection.count_documents({"status": "active"})
return count

# 3. Proper generator typing
from collections.abc import Generator, AsyncGenerator

def stream_data() -> Generator[str, None, None]:
    yield "chunk"

async def astream_data() -> AsyncGenerator[str, None]:
    yield "chunk"

# 4. None checks for optional types
if self.config is None:
    use_defaults()
else:
    value = self.config.some_property

# 5. Type guards for unions
if isinstance(result, dict):
    value = result.get("key")
else:
    value = result.key  # Pydantic model
```

**Pre-commit Validation**: mypy runs automatically on all commits. Fix all errors before committing.

**Learn More**: See the backend CHANGELOG —
[`docs/project/versions/backend/CHANGELOG.md`](../project/versions/backend/CHANGELOG.md) —
for the v0.5.3 type-safety pass and subsequent enforcement bumps.

### Code Organization
```python
"""
Module description goes here.
Explains the purpose and context of this file.
"""

# Standard library imports
import sys
from typing import Any

# Third-party imports
import pandas as pd
from fastapi import FastAPI

# Local imports
from src.core.config import settings
from src.database.mongodb import get_database

# Constants
DEFAULT_TIMEFRAME = "6mo"

# Functions and classes
def process_data(data: pd.DataFrame) -> dict[str, Any]:
    """
    Process financial data.

    Args:
        data: Raw market data DataFrame

    Returns:
        Processed data dictionary

    Raises:
        ValueError: If data is empty or invalid
    """
    # Implementation with rich comments explaining WHY
    pass
```

### Error Handling
```python
# Use specific exceptions
try:
    result = analyze_data(symbol)
except ValueError as e:
    logger.error(f"Invalid symbol: {symbol}", exc_info=e)
    raise
except ConnectionError as e:
    logger.error(f"Database connection failed", exc_info=e)
    # Retry logic here
```

### Logging
```python
import structlog

logger = structlog.get_logger()

# Use structured logging with context
logger.info("Starting analysis", symbol=symbol, timeframe=timeframe)
logger.error("Analysis failed", symbol=symbol, error=str(e))
```

### Async/Await
Prefer async/await for I/O operations:

```python
async def get_market_data(symbol: str) -> dict[str, Any]:
    """Fetch market data asynchronously."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"/api/data/{symbol}")
        return response.json()
```

## TypeScript Standards

### Modern Syntax
- Use ES modules
- Use optional chaining: `data?.fibonacci?.levels`
- Use nullish coalescing: `value ?? defaultValue`
- Use `satisfies` operator for type checking

### Type Definitions
Types are required for all functions and components:

```typescript
interface FibonacciLevel {
  level: number;
  price: number;
  label: string;
}

interface AnalysisResult {
  symbol: string;
  levels: FibonacciLevel[];
  chartUrl?: string;
}

async function analyzeFibonacci(
  symbol: string,
  timeframe: string = '6mo'
): Promise<AnalysisResult> {
  // Implementation
}
```

### React Components
```typescript
/**
 * FibonacciChart component displays Fibonacci retracement levels.
 *
 * Handles user interactions and updates via React Query.
 */
interface FibonacciChartProps {
  symbol: string;
  timeframe: string;
  onAnalysisComplete?: (result: AnalysisResult) => void;
}

export function FibonacciChart({
  symbol,
  timeframe,
  onAnalysisComplete
}: FibonacciChartProps) {
  // Component implementation
  return (
    <div className="fibonacci-chart">
      {/* JSX */}
    </div>
  );
}
```

### Error Handling
```typescript
try {
  const result = await api.analyzeFibonacci(symbol, timeframe);
  setData(result);
} catch (error) {
  if (error instanceof ApiError) {
    toast.error(`API Error: ${error.message}`);
  } else {
    toast.error('An unexpected error occurred');
  }
  console.error('Analysis failed:', error);
}
```

## API Validation Patterns

### Symbol Validation
Always validate symbols before suggesting them to users:

```python
def validate_symbol(symbol: str) -> bool:
    """
    Validate that a symbol has available price data.

    Some symbols exist but lack price data in yfinance.
    Test with ticker.history(period="5d") before returning.
    """
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period="5d")
        return len(history) > 0
    except Exception:
        return False
```

### Root Cause Fix Principle
Fix validation at the source (search endpoint), not downstream (UI):

```python
# ✅ Good: Validate in search endpoint
@app.get("/api/market/search")
async def search_symbols(q: str) -> list[str]:
    candidates = search_provider.search(q)
    # Filter out invalid symbols immediately
    valid_symbols = [s for s in candidates if validate_symbol(s)]
    return valid_symbols

# ❌ Bad: Let invalid symbols through, handle in UI
@app.get("/api/market/search")
async def search_symbols(q: str) -> list[str]:
    return search_provider.search(q)  # May include invalid symbols
```

## React Closure Debugging

React Query mutations capture state at creation time, not execution time.

**Solutions:**
- Pass state via message parameters, not closures
- Use direct parameter passing in mutationFn
- Log both user messages AND parsed parameters

**Debug:** Check Redis cache keys for stale values, add structured logging.

## Data Contract Synchronization

**Critical Rule:** When modifying frontend or backend logic, verify data contract alignment across all layers.

### 4-Layer Contract Checklist
1. **Backend Pydantic Models** - `Literal["value1", "value2"]`
2. **Frontend TypeScript** - `'value1' | 'value2'` (must mirror backend)
3. **User Input Parsing** - Handle new patterns
4. **Business Logic** - Process new values

### Common Failures
- **422 Errors**: TypeScript types don't match Pydantic Literals
- **Silent Fallbacks**: Parsing fails but uses default instead of error

### Debug
Check Pydantic errors in logs, verify types match, test all valid values.

## Development Hot Reload

Hot reload works for ~90-95% of changes. **When in doubt, restart.**

- **Backend**: Most changes hot-reload. Restart for: new dependencies, env changes, module-level code
- **Frontend**: Almost all changes hot-reload. Restart for: new dependencies, vite.config.ts

See [Getting Started](getting-started.md) for detailed hot reload guidelines.

## Testing Standards

### Backend Tests
```python
"""
tests/test_fibonacci_analysis.py

Tests for Fibonacci analysis functionality.
"""
import pytest
from src.analysis.fibonacci import FibonacciAnalyzer

class TestFibonacciAnalyzer:
    """Test suite for Fibonacci analyzer."""

    def test_analyze_valid_symbol(self):
        """Test analysis with valid symbol returns expected structure."""
        analyzer = FibonacciAnalyzer()
        result = analyzer.analyze("AAPL", "6mo")

        assert "levels" in result
        assert "confidence" in result
        assert result["confidence"] > 0.5

    def test_analyze_invalid_symbol(self):
        """Test analysis with invalid symbol raises ValueError."""
        analyzer = FibonacciAnalyzer()

        with pytest.raises(ValueError):
            analyzer.analyze("INVALID", "6mo")
```

### Frontend Tests
```typescript
/**
 * FibonacciChart.test.tsx
 *
 * Tests for FibonacciChart component.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { FibonacciChart } from './FibonacciChart';

describe('FibonacciChart', () => {
  it('renders loading state initially', () => {
    render(<FibonacciChart symbol="AAPL" timeframe="6mo" />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('displays chart after successful analysis', async () => {
    render(<FibonacciChart symbol="AAPL" timeframe="6mo" />);

    await waitFor(() => {
      expect(screen.getByRole('img')).toBeInTheDocument();
    });
  });
});
```

## Commit Standards

### Commit Message Format
```
type(scope): brief description

Longer description if needed.

- Detail point 1
- Detail point 2
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(analysis): Add stochastic oscillator indicator

Implements stochastic oscillator calculation and visualization.

- Calculate %K and %D lines
- Add oversold/overbought zones
- Include in chart generation
```

```
fix(api): Handle empty search results gracefully

Previously crashed when yfinance returned no results.
Now returns empty array with appropriate message.
```

## Security Standards

### Secrets Management
- ❌ Never commit secrets to git
- ✅ Use environment variables (`.env`, gitignored)
- ✅ Use `.env.example` for documentation

### Input Validation
```python
from pydantic import BaseModel, validator

class AnalysisRequest(BaseModel):
    symbol: str
    timeframe: str

    @validator('symbol')
    def validate_symbol(cls, v):
        """Ensure symbol is alphanumeric and uppercase."""
        if not v.isalnum() or not v.isupper():
            raise ValueError('Invalid symbol format')
        return v
```

### Authentication
```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_token(token: str = Depends(security)) -> str:
    """Verify JWT token and return user ID."""
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY)
        return payload['user_id']
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

## Performance Standards

### Database Queries
```python
# ✅ Good: Use indexes and limit results
async def get_recent_analyses(user_id: str, limit: int = 10):
    return await db.analyses.find(
        {"user_id": user_id}
    ).sort("created_at", -1).limit(limit).to_list()

# ❌ Bad: Load everything into memory
async def get_recent_analyses(user_id: str):
    all_analyses = await db.analyses.find({"user_id": user_id}).to_list()
    return sorted(all_analyses, key=lambda x: x['created_at'], reverse=True)[:10]
```

### Caching
```python
# Use Redis for expensive operations
async def get_market_data(symbol: str) -> dict:
    """Get market data with Redis caching."""
    cache_key = f"market_data:{symbol}"

    # Try cache first
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # Fetch and cache
    data = await fetch_from_yfinance(symbol)
    await redis.setex(cache_key, 3600, json.dumps(data))  # 1 hour TTL
    return data
```

## Documentation Standards

### File Documentation
Every module should have a docstring with:
- **Purpose**: What the module does
- **Key Features**: Main capabilities (bullet list)
- **Dependencies**: External packages used

### Function Documentation
Use Google-style docstrings:
```python
def calculate_levels(high: float, low: float) -> dict[str, float]:
    """
    Calculate Fibonacci retracement levels.

    Args:
        high: Swing high price
        low: Swing low price

    Returns:
        Dictionary mapping level names to prices

    Raises:
        ValueError: If high <= low
    """
```

Include: brief description, Args, Returns, Raises, Example (optional).
