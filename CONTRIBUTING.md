# Contributing to Financial Agent Platform

Thank you for your interest in contributing to the Financial Agent Platform! This document provides guidelines and workflows for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Requirements](#testing-requirements)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)
- [Feature Specification Process](#feature-specification-process)
- [Version Management](#version-management)

---

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inclusive environment for all contributors, regardless of experience level, background, or identity.

### Expected Behavior

- Be respectful and constructive in all interactions
- Focus on what is best for the project and community
- Accept feedback gracefully and provide feedback thoughtfully
- Help others learn and grow

### Unacceptable Behavior

- Harassment, discriminatory language, or personal attacks
- Publishing others' private information without permission
- Trolling, insulting/derogatory comments, or unconstructive criticism

---

## Getting Started

### Prerequisites

**Required**:
- **Node.js** 20+ (frontend)
- **Python** 3.12+ (backend)
- **Docker** and **Docker Compose** (local development)
- **Git** with configured user name and email

**Optional** (for cloud deployment):
- **kubectl** (Kubernetes CLI)
- **Azure CLI** (for AKS deployments)
- **Alibaba Cloud CLI** (for DashScope AI services)

### Initial Setup

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/financial_agent.git
   cd financial_agent
   ```

2. **Install Pre-commit Hooks**:
   ```bash
   # Pre-commit hooks enforce code quality automatically
   pip install pre-commit
   pre-commit install
   ```

3. **Start Local Development Environment**:
   ```bash
   # Start all services (backend, frontend, MongoDB, Redis, Langfuse)
   make dev

   # Verify services are running
   curl http://localhost:8000/api/health  # Backend
   curl http://localhost:3000             # Frontend
   ```

4. **Run Tests**:
   ```bash
   # Backend tests
   cd backend && make test

   # Frontend tests (must run in Docker)
   docker compose exec frontend npm test
   ```

**Detailed Setup**: See [Getting Started Guide](docs/development/getting-started.md)

---

## Development Workflow

### 1. Feature Specification (Required for New Features)

**Before implementing any new feature**, create a specification document:

```bash
# Create feature spec
mkdir -p docs/features
touch docs/features/<feature-name>.md
```

**Required Sections**:
- **Context**: Why this feature is needed
- **Problem Statement**: What problem does it solve?
- **Proposed Solution**: Technical approach
- **Implementation Plan**: Step-by-step breakdown
- **Acceptance Criteria**: How to verify success

**Template**: See [Feature Specification Template](docs/features/README.md)

**Process**:
1. Create spec document
2. **Get approval before coding** (discuss in issue or PR)
3. Reference spec during implementation
4. Update spec if design changes

### 2. Make Changes

```bash
# Create feature branch (REQUIRED naming convention)
git checkout -b users/YOUR_USERNAME/feature-name

# Examples of valid branch names:
#   users/danny/add-dark-mode
#   users/allen/fix-login-bug
#   users/john/feature/new-dashboard

# ❌ Invalid branch names (will fail CI):
#   feature/my-feature     # Missing users/{name}/ prefix
#   danny/my-feature       # Missing users/ prefix
#   users/danny            # Missing feature name

# Make changes
# ... edit files ...

# Run quality checks
make fmt    # Format code (Black, Prettier)
make lint   # Lint code (Ruff, ESLint, mypy)
make test   # Run all tests
```

> **⚠️ Branch Naming Policy**: All contributor branches MUST follow the pattern `users/{username}/{feature-name}`. PRs from incorrectly named branches will be automatically rejected by CI.

### 3. Commit Changes

**Commit Message Format**:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring (no functional changes)
- `test`: Adding or updating tests
- `chore`: Maintenance tasks (dependency updates, etc.)

**Examples**:
```bash
feat(backend): add Fibonacci overlay support

Implements automatic Fibonacci retracement calculation and
chart overlay rendering for technical analysis.

Closes #123

---

fix(database): use updated_at for Cosmos DB sorting

Cosmos DB MongoDB API does not support sorting by _id with
compound filters. Changed to use explicit timestamp fields.

Fixes #456
```

**Pre-commit Hooks**: Will automatically run:
- Code formatting (Black, Prettier)
- Linting (Ruff, ESLint, mypy)
- Tests (backend unit tests)
- Version validation (version must be bumped)
- File length checks (max 500 lines)
- Security scans (eslint-plugin-security)

### 4. Version Bumping (Required)

**Every commit must bump at least one version**:

```bash
# Bump backend version
./scripts/bump-version.sh backend patch  # 0.1.0 → 0.1.1
./scripts/bump-version.sh backend minor  # 0.1.0 → 0.2.0
./scripts/bump-version.sh backend major  # 0.1.0 → 1.0.0

# Bump frontend version
./scripts/bump-version.sh frontend patch
```

**Version Files**: You must fill out `docs/project/versions/<component>/v*.md` with:
- Overview of changes
- Features added/removed
- Bug fixes
- Breaking changes
- Migration guide (if applicable)

**See**: [Version Management Guide](docs/project/versions/README.md)

---

## Coding Standards

### Python (Backend)

**Style**: [PEP 8](https://pep8.org/) enforced by **Black** (120 char line length)

**Type Safety**: **mypy** in strict mode
```python
# Type hints are required for all functions
def calculate_fibonacci(
    high: float,
    low: float,
    levels: list[float] = [0.236, 0.382, 0.5, 0.618, 0.786]
) -> dict[str, float]:
    """Calculate Fibonacci retracement levels."""
    ...
```

**Linting**: **Ruff** with strict rules
- No unused imports
- No mutable default arguments
- No bare `except:` clauses

**Testing**: **pytest** with >80% coverage target

**Documentation**: Docstrings for all public functions (Google style)

**See**: [Coding Standards](docs/development/coding-standards.md#python-backend)

### TypeScript (Frontend)

**Style**: **Prettier** with 2-space indentation

**Type Safety**: **TypeScript strict mode**
```typescript
// Explicit types for all function parameters and return values
function calculateFibonacci(
  high: number,
  low: number,
  levels: number[] = [0.236, 0.382, 0.5, 0.618, 0.786]
): Record<string, number> {
  // ...
}
```

**Linting**: **ESLint** with React/TypeScript plugins
- No `any` types (use `unknown` or specific types)
- Prefer functional components with hooks
- No `console.log` in production code

**Testing**: **Vitest** for unit tests, **React Testing Library** for components

**See**: [Coding Standards](docs/development/coding-standards.md#typescript-frontend)

### File Organization

**Max Lines**: 500 lines per file (enforced by pre-commit hook)

**File Structure** (Python example):
```python
"""
Module docstring explaining purpose.
"""

# Standard library imports
from datetime import datetime

# Third-party imports
import numpy as np
from pydantic import BaseModel

# Local imports
from ..models.chat import Chat
from .base_repository import BaseRepository

# Constants
MAX_MESSAGES = 100

# Classes and functions
class ChatRepository(BaseRepository):
    """Repository for chat data access."""
    ...
```

---

## Testing Requirements

### Backend Tests

**Location**: `backend/tests/`

**Run Tests**:
```bash
cd backend
make test           # Run all tests
make test-cov       # Run with coverage report
pytest tests/test_specific.py -v  # Run specific test file
```

**Test Coverage**: Aim for >80% coverage
```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

**Test Patterns**:
- Use `pytest` fixtures for setup/teardown
- Mock external dependencies (MongoDB, Redis, LLM APIs)
- Test both happy path and error cases
- Use `@pytest.mark.asyncio` for async tests

**Example**:
```python
import pytest
from src.services.chat_service import ChatService

@pytest.mark.asyncio
async def test_create_chat(mock_chat_repo, mock_message_repo):
    """Test chat creation with default title."""
    service = ChatService(mock_chat_repo, mock_message_repo)
    chat = await service.create_chat(user_id="user_123")

    assert chat.title == "New Chat"
    assert chat.user_id == "user_123"
    mock_chat_repo.create.assert_called_once()
```

### Frontend Tests

**Location**: `frontend/src/**/*.test.ts(x)`

**Run Tests** (must run in Docker):
```bash
docker compose exec frontend npm test           # Run all tests
docker compose exec frontend npm run test:ui    # Run with UI
docker compose exec frontend npm run test:coverage  # With coverage
```

**Test Patterns**:
- Use **Vitest** for unit tests
- Use **React Testing Library** for component tests
- Test user interactions, not implementation details
- Mock API calls with **MSW** (Mock Service Worker)

**Example**:
```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ChatInput from './ChatInput';

describe('ChatInput', () => {
  it('submits message on enter key', () => {
    const handleSubmit = vi.fn();
    render(<ChatInput onSubmit={handleSubmit} />);

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Test message' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(handleSubmit).toHaveBeenCalledWith('Test message');
  });
});
```

---

## Documentation

### When to Document

**Always**:
- New features (create feature spec)
- Bug fixes (update troubleshooting docs if pattern emerges)
- API changes (update OpenAPI annotations)
- Breaking changes (add migration guide)

**Update These Files**:
- `README.md` - For major features
- `docs/features/` - Feature specifications
- `docs/architecture/` - System design changes
- `docs/troubleshooting/` - Common issues and solutions
- `docs/project/versions/` - Version release notes

### Documentation Style

**Markdown**: Use GitHub-flavored Markdown

**Code Blocks**: Always specify language
````markdown
```python
def example():
    return "Use syntax highlighting"
```
````

**Links**: Use relative links for internal docs
```markdown
See [Deployment Guide](docs/deployment/workflow.md) for details.
```

**Examples**: Provide code examples for all new features

---

## Pull Request Process

### 1. Before Creating PR

✅ **Checklist**:
- [ ] Feature spec created (for new features)
- [ ] Code follows style guidelines (`make fmt`)
- [ ] All tests pass (`make test`)
- [ ] Linting passes (`make lint`)
- [ ] Version bumped (required)
- [ ] Version documentation file filled out
- [ ] No secrets in code (API keys, passwords, etc.)
- [ ] Documentation updated

### 2. Create Pull Request

**Title Format**:
```
<type>(<scope>): <short description>
```

**Description Template**:
```markdown
## Context
<!-- Why is this change needed? -->

## Changes
<!-- What changed? -->
- Added X feature
- Fixed Y bug
- Updated Z documentation

## Testing
<!-- How was this tested? -->
- [ ] Unit tests pass
- [ ] Manual testing completed
- [ ] Integration tests pass (if applicable)

## Related Issues
Closes #123
Relates to #456

## Screenshots (if UI changes)
<!-- Add screenshots or GIFs -->
```

### 3. Code Review

**Expect Feedback On**:
- Code quality and readability
- Test coverage
- Performance considerations
- Security implications
- Documentation completeness

**Respond to Feedback**:
- Address all comments (agree/disagree respectfully)
- Push additional commits to the same branch
- Mark conversations as resolved when addressed

### 4. Merge Requirements

**Required Approvals**: 1 approving review

**CI Checks Must Pass**:
- ✅ Branch Policy (branch name matches `users/{username}/{feature}`)
- ✅ Unit Tests (backend pytest + frontend tests)
- ✅ Linting (Ruff, Black, ESLint, TypeScript)
- ✅ No merge conflicts
- ✅ Version bumped

**Branch Protection Rules** (enforced on `main`):
- Direct push to `main` is **blocked** (except for repo admins)
- All changes must go through Pull Request
- 1 approving review required before merge
- "Unit Tests" status check must pass
- Stale reviews are dismissed on new commits

**Merge Strategy**: Squash and merge (default)

**Auto-Deployment**: Once merged to `main`, changes are automatically deployed to production (ACK cluster).

---

## Feature Specification Process

### When to Create a Spec

**Required**:
- New user-facing features
- Significant refactoring (>500 lines changed)
- API changes
- Database schema changes

**Optional** (but recommended):
- Bug fixes with design implications
- Performance optimizations

### Spec Review Process

1. **Draft Spec**: Create in `docs/features/`
2. **Discussion**: Open GitHub issue linking to spec
3. **Review**: Maintainers provide feedback
4. **Approval**: Spec approved before implementation starts
5. **Implementation**: Code PR references spec
6. **Update**: Spec updated if design changes during implementation

**Template**: [docs/features/README.md](docs/features/README.md)

---

## Version Management

### Semantic Versioning

We use [Semantic Versioning](https://semver.org/):

```
MAJOR.MINOR.PATCH

1.2.3
│ │ │
│ │ └─ Patch: Bug fixes, no API changes
│ └─── Minor: New features, backward compatible
└───── Major: Breaking changes
```

### Component Versioning

**Backend and Frontend are versioned independently**:

```bash
# Backend v0.5.5, Frontend v0.8.4
# They don't need to match!
```

**Compatibility**: See [Version Matrix](docs/project/versions/VERSION_MATRIX.md)

### Changelog Maintenance

**Auto-generated**: Changelog updated automatically by `bump-version.sh`

**Manual Edits**: You must fill out version file with details:
- Overview of changes
- Features added
- Bug fixes
- Breaking changes
- Migration instructions

**Location**:
- `docs/project/versions/backend/CHANGELOG.md`
- `docs/project/versions/frontend/CHANGELOG.md`
- `docs/project/versions/backend/v*.md` (per-version details)

---

## Getting Help

### Documentation

- **Getting Started**: [docs/development/getting-started.md](docs/development/getting-started.md)
- **Coding Standards**: [docs/development/coding-standards.md](docs/development/coding-standards.md)
- **Troubleshooting**: [docs/troubleshooting/README.md](docs/troubleshooting/README.md)
- **Architecture**: [docs/architecture/system-design.md](docs/architecture/system-design.md)

### Ask Questions

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and general discussion
- **Pull Request Comments**: For specific code questions

### Community

- Be patient - maintainers are volunteers
- Search existing issues before creating new ones
- Provide context and examples in questions
- Help others when you can

---

## Recognition

Contributors are recognized in:
- Release notes for their contributions
- Git commit history (Co-Authored-By tags)
- This project's ongoing success!

---

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see LICENSE file).

---

**Thank you for contributing to Financial Agent Platform!** 🚀

Your contributions help make financial analysis accessible through AI-powered tools.
