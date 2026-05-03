# Error Handling & Debugging Guide

## Overview

This document explains our custom exception system and debugging improvements designed to reduce Mean Time To Resolution (MTTR) for production issues.

## Problem We're Solving

**Before (Generic Errors):**
```python
# All errors look the same
try:
    db.connect()
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))  # ❌ All 500 errors

# Result: Hard to debug
# - Is this a database issue?
# - Is this a configuration issue?
# - Is this a third-party API issue?
# Developer spends 20 minutes checking logs, MongoDB, network...
```

**After (Typed Errors):**
```python
# Clear error categorization
try:
    db.connect()
except InvalidNamespace as e:
    raise DatabaseError(f"Invalid DB name: {e}", db_name=parsed_name)  # ✅ 500 with context

# Result: Fast debugging
# - See "error_type": "database_error" in logs
# - See "db_name": "_test?ssl=true" in context
# - Immediately know it's a config issue (query params in DB name)
# Developer fixes in 2 minutes
```

---

## Exception Hierarchy

### Base Class: `AppError`

All custom exceptions inherit from `AppError`:

```python
from src.core.exceptions import AppError

class AppError(Exception):
    status_code: int = 500  # Default HTTP status
    error_type: str = "internal_error"  # Error category for logging

    def __init__(self, message: str, **context):
        self.message = message
        self.context = context  # Additional debugging data

    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "status_code": self.status_code,
            **self.context
        }
```

---

## Error Categories

### 400-Level: Client Errors (User's Fault)

#### `ValidationError` (400)
**Use when:** User provided invalid input

```python
from src.core.exceptions import ValidationError

# Bad email format
if not email_regex.match(email):
    raise ValidationError("Invalid email format", email=email)

# Missing required field
if not username:
    raise ValidationError("Username is required")
```

**HTTP Response:**
```json
{
  "status": 400,
  "error_type": "validation_error",
  "detail": "Invalid email format"
}
```

#### `AuthenticationError` (401)
**Use when:** Login credentials invalid

```python
from src.core.exceptions import AuthenticationError

if not verify_password(password, user.password_hash):
    raise AuthenticationError("Invalid username or password")
```

#### `AuthorizationError` (403)
**Use when:** User lacks permission

```python
from src.core.exceptions import AuthorizationError

if user.role != "admin":
    raise AuthorizationError("Admin access required", user_id=user.id)
```

#### `NotFoundError` (404)
**Use when:** Resource doesn't exist

```python
from src.core.exceptions import NotFoundError

user = await user_repo.get(user_id)
if not user:
    raise NotFoundError("User not found", user_id=user_id)
```

#### `RateLimitError` (429)
**Use when:** User exceeded rate limit

```python
from src.core.exceptions import RateLimitError

if request_count > limit:
    raise RateLimitError("Rate limit exceeded", limit=limit, window="1 minute")
```

---

### 500-Level: Server Errors (Our Fault)

#### `DatabaseError` (500)
**Use when:** MongoDB, Redis, or database operations fail

```python
from src.core.exceptions import DatabaseError

# Connection failed
try:
    await client.admin.command("ping")
except Exception as e:
    raise DatabaseError(f"MongoDB connection failed: {e}") from e

# Invalid collection name
if "?" in db_name:
    raise DatabaseError(
        "Database name contains query parameters",
        raw_db_name=db_name_with_params,
        parsed_db_name=parsed_name
    )

# Query failed
try:
    result = await collection.find_one({"user_id": user_id})
except Exception as e:
    raise DatabaseError(f"Query failed: {e}", user_id=user_id) from e
```

**Logs:**
```json
{
  "error_type": "database_error",
  "message": "Database name contains query parameters",
  "status_code": 500,
  "raw_db_name": "_test?ssl=true&retryWrites=true",
  "parsed_db_name": "_test"
}
```

#### `CacheError` (500)
**Use when:** Redis cache operations fail

```python
from src.core.exceptions import CacheError

try:
    await redis.set(key, value)
except Exception as e:
    raise CacheError(f"Failed to set cache: {e}", key=key) from e
```

#### `ConfigurationError` (500)
**Use when:** Application misconfigured (usually startup errors)

```python
from src.core.exceptions import ConfigurationError

# Missing environment variable
if not settings.secret_key:
    raise ConfigurationError("SECRET_KEY environment variable not set")

# Invalid configuration value
if settings.rate_limit_window <= 0:
    raise ConfigurationError(
        "Invalid rate limit window",
        value=settings.rate_limit_window
    )
```

---

### 503: External Service Errors (Third-Party's Fault)

#### `ExternalServiceError` (503)
**Use when:** External APIs (Tencent, yfinance, DashScope) fail

```python
from src.core.exceptions import ExternalServiceError

# API timeout
try:
    response = await client.send_email(to=email, subject=subject)
except TimeoutError as e:
    raise ExternalServiceError(
        "Email service timeout",
        service="tencent_ses",
        timeout_seconds=30
    ) from e

# API rate limit
if response.status_code == 429:
    raise ExternalServiceError(
        "Email service rate limit exceeded",
        service="tencent_ses",
        retry_after=response.headers.get("Retry-After")
    )

# API error
if response.status_code >= 500:
    raise ExternalServiceError(
        f"Email service error: {response.text}",
        service="tencent_ses",
        status_code=response.status_code
    )
```

**HTTP Response:**
```json
{
  "status": 503,
  "error_type": "external_service_error",
  "detail": "Email service timeout"
}
```

**Logs:**
```json
{
  "error_type": "external_service_error",
  "message": "Email service timeout",
  "status_code": 503,
  "service": "tencent_ses",
  "timeout_seconds": 30
}
```

---

## Debugging Improvements

### 1. MongoDB Database Name Validation

**Problem:** Database name contained query parameters (`_test?ssl=true`), causing `InvalidNamespace` errors that were hard to diagnose.

**Solution:**
```python
# backend/src/database/mongodb.py

# Validate database name
if any(char in database_name for char in ["?", "&", "="]):
    logger.error(
        "Invalid database name: contains query parameter characters",
        raw_value=raw_db_name,
        parsed_value=database_name,
    )
    raise ConfigurationError(
        f"Database name '{database_name}' contains invalid characters",
        raw_db_name=raw_db_name,
        parsed_db_name=database_name
    )

# Log successful parsing
if db_with_params != database_name:
    logger.info(
        "Database name extracted from URL",
        raw_url_suffix=db_with_params,
        parsed_db_name=database_name
    )
```

**Before:** 15 minutes debugging "InvalidNamespace" error
**After:** 2 minutes - see `ConfigurationError` with both raw and parsed values

---

### 2. Frontend API URL Logging

**Problem:** Frontend silently used wrong API URL, causing 404 errors.

**Solution:**
```typescript
// frontend/src/main.tsx

const API_BASE_URL = import.meta.env.VITE_API_URL || ""
console.info('[Config] API_BASE_URL:', API_BASE_URL || '(empty - will use relative URLs)')
console.info('[Config] Environment:', import.meta.env.MODE)
```

**Before:** 20 minutes checking network tab, verifying env vars
**After:** 1 minute - open browser console, see API_BASE_URL value immediately

---

### 3. Error Type in Logs

**Problem:** All 500 errors looked the same in logs, hard to categorize.

**Solution:** Every error now has `error_type` field:

```json
{
  "level": "error",
  "timestamp": "2025-10-07T12:34:56Z",
  "message": "Application error occurred",
  "path": "/api/auth/register",
  "method": "POST",
  "error_type": "database_error",  // ← Easy to filter/alert on
  "status_code": 500,
  "raw_db_name": "_test?ssl=true",
  "parsed_db_name": "_test"
}
```

**Monitoring queries:**
```bash
# Find all database errors
kubectl logs -f deployment/backend | jq 'select(.error_type == "database_error")'

# Find all external service errors
kubectl logs -f deployment/backend | jq 'select(.error_type == "external_service_error")'

# Alert on configuration errors (should only happen at startup)
kubectl logs -f deployment/backend | jq 'select(.error_type == "configuration_error")'
```

---

## Adding New Error Types

The system is designed to be extensible. Add new exceptions as needed:

```python
# backend/src/core/exceptions.py

class StorageError(AppError):
    """Cloud storage (OSS/S3) operation failed."""
    status_code = 500
    error_type = "storage_error"


class ChartGenerationError(AppError):
    """Chart rendering failed (matplotlib/plotting issue)."""
    status_code = 500
    error_type = "chart_generation_error"


class LLMError(ExternalServiceError):
    """LLM API (DashScope, OpenAI) failed."""

    def __init__(self, message: str, model: str, **context):
        super().__init__(message, service="llm", model=model, **context)
```

**Usage:**
```python
from src.core.exceptions import ChartGenerationError

try:
    chart = generate_fibonacci_chart(symbol, data)
except ValueError as e:
    raise ChartGenerationError(
        f"Invalid data for chart: {e}",
        symbol=symbol,
        data_points=len(data)
    ) from e
```

---

## Best Practices

### 1. Always Add Context

```python
# ❌ Bad: No context
raise DatabaseError("Query failed")

# ✅ Good: Add debugging context
raise DatabaseError(
    "Query failed: duplicate key",
    user_id=user_id,
    username=username,
    operation="create_user"
)
```

### 2. Preserve Original Exception

```python
# ❌ Bad: Loses stack trace
try:
    await db.connect()
except Exception as e:
    raise DatabaseError(str(e))

# ✅ Good: Preserves stack trace
try:
    await db.connect()
except Exception as e:
    raise DatabaseError(f"Connection failed: {e}") from e
```

### 3. Use Specific Exceptions

```python
# ❌ Bad: Generic AppError
raise AppError("User not found")

# ✅ Good: Specific NotFoundError (404)
raise NotFoundError("User not found", user_id=user_id)
```

### 4. Log Before Raising (If Needed)

```python
# For critical errors, log before raising
if "?" in database_name:
    logger.error(
        "Invalid database name",
        raw_value=raw_db_name,
        parsed_value=database_name
    )
    raise ConfigurationError(
        "Database name contains invalid characters",
        raw_db_name=raw_db_name
    )
```

---

## Summary

| Error Type | Status | When to Use | Example |
|------------|--------|-------------|---------|
| `ValidationError` | 400 | Invalid user input | Bad email format |
| `AuthenticationError` | 401 | Login failed | Wrong password |
| `AuthorizationError` | 403 | Lacks permission | Non-admin accessing admin endpoint |
| `NotFoundError` | 404 | Resource missing | User ID doesn't exist |
| `RateLimitError` | 429 | Too many requests | Exceeded 100 req/min |
| `DatabaseError` | 500 | DB operation failed | MongoDB connection timeout |
| `CacheError` | 500 | Redis error | Cache set failed |
| `ConfigurationError` | 500 | Misconfigured app | Missing env var |
| `ExternalServiceError` | 503 | Third-party API failed | Tencent SES timeout |

**Key Benefits:**
1. **Faster debugging**: Error type immediately identifies problem category
2. **Better monitoring**: Filter/alert on specific error types
3. **Proper HTTP codes**: 500 vs 503 vs 400 makes troubleshooting obvious
4. **Rich context**: Every error includes relevant debugging data
5. **Scalable**: Easy to add new error types as app grows
