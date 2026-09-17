---
title: A Citation Is Not Evidence Verification
status: in-progress
version: backend@0.56.0, frontend@0.37.0
last_updated: 2026-09-17
owner: maintainer
related_paths:
  - backend/src/services/evidence/
  - backend/src/database/repositories/evidence_repository.py
  - backend/src/agent/tools/alpha_vantage/fundamentals.py
  - frontend/src/components/portfolio/EvidencePanel.tsx
---

# A Citation Is Not Evidence Verification

> **TL;DR (EN)**: A citation-shaped token does not prove a number, its unit, its
> economic period, or when it was knowable. IDQ-004 seals normalized records and
> checks explicit structured claims against that immutable manifest. The UI says
> “fields match,” not “the report is true”; source truth, free prose and investment
> conclusions are deliberately outside that mechanical check.
>
> **TL;DR (中文)**：长得像引用的 token 不能证明数字、单位、经济期间或首次可知时间。
> IDQ-004 封存标准化记录，再校验显式结构化主张。UI 只说“字段匹配”，不说“报告真实”；
> 来源本身的真实性、自由文本推论和投资结论仍不能由机械匹配自动证明。

## 1. Context

The account-risk work now preserves dated portfolio inputs, but research still used
same-day aliases and prose warnings. Summaries could remove warning text. Later
phases could fetch changed data. Legacy aliases could refer to more than one quote.
The maintainer prioritized 004 → 005 → 001-B, keeping Stage A containment intact.

## 2. Investigation

A failing regression showed an actual attribution bug: an AlphaVantage-named service
returned a Yahoo `_source` payload, while its tool appended `Source: alphavantage`.
The service's class name had been confused with the provider that supplied the data.
The fix preserves payload attribution instead of adding another cosmetic citation.

We kept the existing DataManager/provider fallback chains and added a sealed-tool
scope at composition boundaries, avoiding edits to the oversized DataManager/ReAct
implementation. Real browser research returned canonical IDs, not invented fixtures
at the API layer. A conflict scenario initially selected Yahoo's extended-hours-first
path because only the risk clock was fixed; pinning the fixture's market-session
clock made the two intended **same-session closing** receipts actually comparable.
No production provider priority was changed to force that test green.

Final review found another important ambiguity: old provider adapters can return an
empty list after failure. Treating that as an available zero-item fact would fabricate
“no news/filings.” A failing regression now requires missing coverage for those empty
legacy lists. Evidence images were rebuilt after this correction, not relabeled green.

## 3. Root Cause

- Retrieval time was easy to mistake for observation/publication time.
- Aliases encoded a day, not an immutable evidence identity.
- Numeric prose and a valid citation token had no typed claim-to-record relationship.
- Model agreement and a successful tool call could be mistaken for factual verification.
- A translated warning was not durable structured quality metadata.

## 4. Fix

Each symbol gets one bounded snapshot aggregate with a collecting lease/generation,
then one atomic seal. Generation CAS fences stale collectors. Sealed retries preserve
the original records; explicit child manifests retain parent records and conflicting
revisions. Separate immutable dossiers bind report hash, manifest hash and claim edges.
No read API consumes collecting/failed/cancelled snapshots as sealed evidence.

Adapters capture only normalized financial fields through the existing providers.
They retain missing units, publication times and unsupported PIT capability instead
of filling them from fetch time. Source links are allowlisted HTTPS links without
userinfo/query credentials, never arbitrary fetch proxies or local file paths.

Portfolio and Deep tool calls inside the sealed scope cannot fetch a new symbol or
fresh unsupported data. A separate canonical reminder survives narrative truncation.
The validator checks membership, symbol, metric, unit, economic period, cutoff,
quality/conflict and value. Derived claims use a small named calculator registry;
formula strings are never evaluated. Invalid/missing material claims retain explicit
assessment reasons even if a model or translation removes prose warnings.

## 5. Verification Boundary and Lessons

1. `matches_snapshot` means structured fields agree with captured records. It does
   **not** certify a hostile/misleading sentence surrounding those fields.
2. The provider can still be wrong. Presenting its receipt is traceability, not an
   independent audit of the original filing or a general factual verifier.
3. Current TTM/adjusted history is not proven historical PIT; strict historical
   validation rejects it. Unknown periods, units or timestamps remain unknown.
4. Tools outside the current typed adapter scope return unsupported inside a sealed
   run rather than silently fetching uncaptured facts. Strategy-required coverage and
   freshness belong to IDQ-005; evidence collection alone never grants ready/approval.
5. The change adds no broker execution, personal policy defaults, paid live probes,
   or claim of investment effectiveness.

Local validation passes backend 2180 / frontend 271 tests and 33 final image-only
browser scenarios, including Deep reload. Two post-review builds match dependency,
asset and source manifests. A sealed API response survives actual backend recreation
unchanged. The live account's private login/routing/policy state was preserved; no live
inference was requested. Hosted publication is pending. See the
[feature record](../features/investment-evidence-snapshots.md) for current receipts.
