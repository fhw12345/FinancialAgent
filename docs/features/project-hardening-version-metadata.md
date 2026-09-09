---
title: Authoritative Runtime Version Metadata
status: in-progress
version: backend@0.51.5, frontend@0.32.5
last_updated: 2026-09-09
owner: maintainer
related_paths:
  - backend/src/core/version.py
  - backend/src/core/provenance.py
  - backend/src/evals/schemas.py
  - backend/src/evals/live_schemas.py
  - backend/src/evals/reporting.py
  - scripts/check-runtime-versions.py
  - frontend/e2e/project-hardening.spec.ts
  - docs/architecture/overview.md
---

# PH-010: Authoritative Runtime Version Metadata

## Scope and Contract

Backend package metadata and frontend `package.json` are authoritative. Runtime
components must not duplicate release strings. Backend development reads the
source pyproject; images without that file read installed package metadata.
Missing metadata is explicitly `0.0.0+development`, never the old `0.1.0` placeholder.

Root, Health and OpenAPI expose the backend version. Health displays both
component versions. Vite derives its constant from the frontend package file.
The architecture overview records the current candidate versions and links to
the package sources rather than introducing another runtime authority.

## Evaluation Provenance

New deterministic and live reports capture provenance once when execution starts:

- `backend_version` from the authoritative accessor;
- `git_commit` when a valid 40-hex revision is available;
- `source`: `build`, `git` or `unknown`;
- `dirty`: local Git status when known, otherwise null.

A declared `FINANCIAL_AGENT_COMMIT` or CI `GITHUB_SHA` is validated syntactically
and labelled `build`, not represented as independently verified Git state.
Otherwise local Git is queried off the event loop with bounded timeouts. Missing
Git/source metadata, failed status, and slow mounts remain unknown, not clean.

The same identity survives live initial/progress/final, failed and budget-exhausted
reports, and JSON/Markdown exports. Historical reports lacking provenance load
with `provenance=null`; deserialization must never attribute an old report to the
current release. No model/provider call is needed to collect this metadata.

## History and Closeout Findings

Commit `960d29a` added the version accessor and Health UI. Earlier screenshots
mocked backend versions and were not real endpoint-consistency evidence.
The 2026-09-09 continuation added installed/source-missing fallback coverage,
real root/Health/OpenAPI consistency checks with mismatch controls, and evaluation
provenance including historical compatibility.

## Validation

- `test_version.py`: source, installed and missing-package paths;
- `scripts/tests/test_hardening_checks.py`: intentional endpoint mismatch and
  degraded Health are rejected;
- `test_evaluation_provenance.py`: validated revision, dirty/unknown local Git,
  deterministic/live exports, progress/final/budget continuity, legacy unknown;
- `test_evaluation_api.py`: initial/terminal/failure reports preserve identity;
- `scripts/check-runtime-versions.py`: real root, Health and OpenAPI match source;
- real browser Health checks both visible versions against package metadata;
- real browser-triggered eval checks report provenance against backend Health.

[Version diagnostics screenshot](assets/ph-010/01-version-diagnostics.png) was
captured on the final rebuilt backend `0.51.5` / frontend `0.32.5` stack, with real
MongoDB/Redis and no mocked Health/version responses. Application source and
runtime dependencies were not bind-mounted. The mocked UI regression no longer
writes this screenshot.

The complete local backend/frontend suites and fresh-image browser selection pass;
see [PH-004](project-hardening-ci-agent-quality-gates.md) and its
[clean-build receipts](assets/ph-004/clean-build-validation.json).
Tested tree: `ddf4284` plus the closeout implementation pending commit.

## Acceptance Criteria

- [x] Runtime release metadata no longer uses the `0.1.0` placeholder.
- [x] Package metadata, root/Health/OpenAPI and UI diagnostics agree.
- [x] Architecture overview reflects candidate versions.
- [x] Consistency tests reject drift.
- [x] Real browser diagnostics and screenshot pass.
- [x] New eval reports retain release provenance without rewriting history.
- [ ] Commit hashes, hosted CI and publication complete.

## Publication Status and Risks

Local acceptance is verified, not shipped. GitHub authorization/real PR evidence
and the publication workflow are still required. Unknown provenance is intentional
when a runtime image has neither Git metadata nor a declared build revision.
Version collection describes the execution environment; it is not a signed build
attestation. Parallel branches must coordinate their component version bumps.
