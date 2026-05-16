# Version Management System

> This directory tracks per-component changelogs. Backend and frontend are
> versioned independently following Semantic Versioning 2.0. The full
> documentation policy (frontmatter, status enum, dates) lives in
> [docs/development/documentation.md](../../development/documentation.md).

## Overview

Financial Agent uses **independent semantic versioning** for backend and frontend components, enabling separate deployment cycles while maintaining compatibility tracking.

## Version Format

We follow [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH

Example: 0.2.1
```

### When to Increment

- **MAJOR** (X.0.0): Breaking changes
  - Breaking API changes (endpoints removed/changed)
  - Database schema changes requiring migration
  - Incompatible frontend/backend changes

- **MINOR** (0.X.0): New features (backward-compatible)
  - New API endpoints
  - New features
  - Non-breaking enhancements

- **PATCH** (0.0.X): Bug fixes
  - Bug fixes
  - Performance improvements
  - Documentation updates
  - Dependency updates (non-breaking)

## Independent Versioning

**Backend** and **Frontend** maintain separate version numbers:

```
Backend:  0.2.1
Frontend: 0.3.0
```

This allows:
- ✅ Independent deployment schedules
- ✅ Faster iteration on UI without backend changes
- ✅ Backend API evolution without forcing frontend updates
- ✅ Clear component ownership

## Version Enforcement Rules

### Critical Rule: No Duplicate Versions

**Every commit must increment at least one component's version.**

Valid scenarios:
- ✅ Backend 0.1.0 → 0.1.1 (backend-only change)
- ✅ Frontend 0.1.0 → 0.1.1 (frontend-only change)
- ✅ Both increment (full-stack feature)

Invalid scenarios:
- ❌ No version change (blocked by pre-commit hook)
- ❌ Version decrement (blocked)

### Pre-commit Validation

The pre-commit hook (`scripts/validate-version.sh`) checks:
1. At least one component version has incremented
2. Version follows semantic versioning format
3. New version > previous version
4. Git tag doesn't already exist

## Image Tag Alignment

Docker images use semantic version tags matching source code:

```bash
backend:0.2.1
frontend:0.3.0
```

## Version Workflow

### 1. Make Code Changes

```bash
# Work on feature/bugfix
vim backend/src/api/endpoints.py
```

### 2. Bump Version

Use the interactive version bumping tool:

```bash
# Backend changes
./scripts/bump-version.sh backend patch   # 0.1.0 → 0.1.1
./scripts/bump-version.sh backend minor   # 0.1.1 → 0.2.0
./scripts/bump-version.sh backend major   # 0.2.0 → 1.0.0

# Frontend changes
./scripts/bump-version.sh frontend patch  # 0.1.0 → 0.1.1
```

The script:
- Updates `package.json` or `pyproject.toml`
- Prompts for changelog entry
- Updates CHANGELOG.md
- Creates version documentation file

### 3. Commit Changes

```bash
git add .
git commit -m "feat: Add new analysis endpoint"

# Pre-commit hook validates version increment
```

### 4. Tag Release

```bash
# Tag with component prefix
git tag backend-v0.2.0
git tag frontend-v0.1.1
```

## Documentation Structure

```
docs/project/versions/
├── README.md                    # This file
├── backend/
│   └── CHANGELOG.md            # Backend version history
└── frontend/
    └── CHANGELOG.md            # Frontend version history
```

### Changelog Format

Each component maintains a CHANGELOG.md following [Keep a Changelog](https://keepachangelog.com/):

```markdown
# Changelog

## [0.2.0] - 2025-10-04

### Added
- New fundamental analysis endpoint
- Stochastic oscillator indicator

### Changed
- Improved error handling for invalid symbols

### Fixed
- Dividend yield validation for MSFT
```

> **Note**: CHANGELOG.md files are the primary version history record.

## Best Practices

### 1. Version Early, Version Often
- Don't batch multiple features into one version
- Smaller, frequent versions are easier to track and rollback

### 2. Document Breaking Changes
- Always document what breaks and how to migrate
- Add migration guides for database schema changes

### 3. Use Git Tags
- Tag every release: `backend-v0.2.0`, `frontend-v0.1.1`
- Tags enable easy rollback and history tracking

### 4. Test Before Tagging
- Run full test suite: `make test`
- Verify linting: `make lint`
- Build docker images successfully

### 5. Keep Changelogs Updated
- Write changelog entries as you code
- Use conventional commit messages to auto-generate changelogs

## Troubleshooting

### Version Validation Failed

**Error**: `Pre-commit hook: Version must be incremented`

**Solution**:
```bash
# Check current versions
cat backend/pyproject.toml | grep version
cat frontend/package.json | grep version

# Bump appropriate version
./scripts/bump-version.sh backend patch
```

### Git Tag Already Exists

**Error**: `fatal: tag 'backend-v0.1.0' already exists`

**Solution**: You're trying to use a duplicate version. Increment further:
```bash
./scripts/bump-version.sh backend patch  # Try next version
```

## Future Enhancements

- [ ] Automated version bumping via GitHub Actions
- [ ] Automatic changelog generation from commit messages
- [ ] Version compatibility testing in CI
- [ ] Automated rollback on failed deployments
- [ ] Release notes generation for GitHub releases
