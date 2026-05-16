# Contributing to Financial Agent

> Personal single-user local fork. This file documents the development
> workflow for the maintainer; there is no external contribution flow.

## Contents

- [Setup](#setup)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Pre-Commit Checklist](#pre-commit-checklist)
- [Feature Specs](#feature-specs)
- [Version Management](#version-management)

---

## Setup

**Required**:

- Docker + Docker Compose
- Node.js 20+ (only if running frontend outside Docker)
- Python 3.12+ (only if running backend outside Docker)
- Git

```bash
git clone <repo>
cd financial_agent
pip install pre-commit && pre-commit install
make dev                                  # start the stack
curl http://localhost:8000/api/health
```

See [docs/development/getting-started.md](docs/development/getting-started.md)
for details.

---

## Development Workflow

### 1. Feature Spec (for non-trivial work)

```bash
touch docs/features/<feature-name>.md
```

Required sections: Context, Problem Statement, Proposed Solution,
Implementation Plan, Acceptance Criteria. Template:
[docs/features/README.md](docs/features/README.md).

### 2. Branch & Edit

```bash
git checkout -b feature/<feature-name>
# ... edit ...
make fmt && make lint && make test
```

### 3. Commit

Conventional commit format:

```
<type>(<scope>): <subject>

<body>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

Pre-commit hooks run automatically:

- Black / Prettier formatting
- Ruff / ESLint / mypy
- Backend pytest
- Version bump check
- 500-line per-file cap
- Security scan (eslint-plugin-security)

### 4. Bump Version (required every commit)

```bash
./scripts/bump-version.sh backend  patch    # 0.1.0 → 0.1.1
./scripts/bump-version.sh frontend minor
```

Fill out the matching `docs/project/versions/<component>/v*.md` with what
changed. See [Version Management](docs/project/versions/README.md).

---

## Coding Standards

### Python (backend)

- Black, 120 char line length
- Type hints required; mypy in strict mode
- Ruff with strict rules (no unused imports, no mutable defaults, no bare `except:`)
- pytest, target >80% coverage on core logic
- Google-style docstrings on public functions

### TypeScript (frontend)

- Prettier, 2-space
- `strict` mode; no `any`
- ESLint with React + TypeScript plugins
- Vitest + React Testing Library
- No `console.log` in committed code

### File Organization

- Max 500 lines per file (enforced)
- Standard import grouping: stdlib → third-party → local

See [docs/development/coding-standards.md](docs/development/coding-standards.md).

---

## Testing

### Backend

```bash
cd backend
make test                                       # all
make test-cov                                   # with coverage
pytest tests/test_specific.py -v                # single file
pytest --cov=src --cov-report=html              # html report
```

Patterns: `pytest` fixtures; `AsyncMock` for async deps; mock Mongo / Redis /
LLM calls at the boundary; test both happy path and errors.

### Frontend

Frontend tests must run inside the container:

```bash
docker compose exec frontend npm test
docker compose exec frontend npm run test:ui
docker compose exec frontend npm run test:coverage
```

Use React Testing Library for components, MSW for API mocks.

---

## Documentation

Update docs when:

- Adding a new feature (write a spec in `docs/features/<name>.md` with YAML
  frontmatter; `status: planning` → `in-progress` → `shipped`)
- Changing behavior of a shipped feature (bump `last_updated` and `version:`
  on the matching `docs/features/<name>.md`)
- Changing an API surface (the API reference at
  `docs/architecture/api-reference.md` points at OpenAPI as source of truth;
  update it if you add a new top-level route group)
- Introducing a breaking change (add a migration note in the matching
  `docs/project/versions/<component>/v*.md`)

Style: GitHub-flavored Markdown, language-tagged code fences, relative links
for internal references. The full ruleset (frontmatter schema, status enum,
date format, case-study template) lives in
[docs/development/documentation.md](docs/development/documentation.md).

---

## Pre-Commit Checklist

- [ ] Tested locally (browser / terminal)
- [ ] `make fmt && make lint && make test` pass
- [ ] Version bumped via `./scripts/bump-version.sh`
- [ ] Version file `docs/project/versions/<component>/v*.md` filled in
- [ ] CHANGELOG entry added
- [ ] No secrets staged (`git diff --staged` scanned for keys)
- [ ] Docs updated

---

## Feature Specs

Required for:

- New user-facing features
- Refactors > ~500 lines
- API or database schema changes

Optional but recommended for bug fixes with design implications or perf work.

Workflow: draft spec in `docs/features/` → implement against it → update the
spec if the design shifts mid-implementation.

---

## Version Management

Semantic versioning per component (backend and frontend version
independently). See
[docs/project/versions/README.md](docs/project/versions/README.md) for the
component-versioning policy and per-component changelogs.

Each version writes to:

- `docs/project/versions/<component>/CHANGELOG.md`
- `docs/project/versions/<component>/v*.md` (overview, changes, breaking
  changes, migration notes)
