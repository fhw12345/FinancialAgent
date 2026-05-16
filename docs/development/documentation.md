---
title: Documentation Standards
status: shipped
version: n/a
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - docs/README.md
  - docs/features/README.md
  - CLAUDE.md
  - CONTRIBUTING.md
---

# Documentation Standards

This document is the source of truth for **how this repo writes docs**. Every
file under `docs/` (and a few outside it) is expected to follow the rules
below. The top-level `CLAUDE.md` carries a 20-line summary that points back
here.

## 1. Directory Layout

```
docs/
├── README.md                     # Index. Update on every doc add/rename/delete.
├── FAQ.md                        # ≥ 10 onboarding Q&A.
├── architecture/                 # System design, agent graph, API reference.
├── development/                  # Getting started, coding standards, this doc.
├── features/                     # One spec per shipped/planned feature.
├── case-studies/                 # Real bugs / design decisions (bilingual TL;DR).
├── archive/                      # Historical PRDs and superseded designs.
└── project/
    └── versions/                 # Per-component CHANGELOG.md and version notes.
```

Rules:

- **No new top-level directories** without updating this file and `docs/README.md`.
- **No `superpowers/`, `interview/`, or `prd/`** — those names have been retired.
  Real PRDs go under `docs/features/<feature-name>.md`; historical PRDs go to
  `docs/archive/`.

## 2. Frontmatter Schema

Every file under `docs/features/`, `docs/development/`, `docs/architecture/`,
and `docs/case-studies/` MUST start with a YAML frontmatter block:

```yaml
---
title: <human-readable title>
status: draft | planning | in-progress | shipped | superseded
version: backend@<x.y.z>, frontend@<x.y.z>   # use "n/a" if not applicable
last_updated: 2026-05-16                      # ISO YYYY-MM-DD
owner: maintainer
related_paths:
  - <repo-relative path>
  - <repo-relative path>
---
```

Exempt from frontmatter:

- `docs/README.md` and category-level `README.md` files (e.g. `docs/features/README.md`).
- `docs/archive/*.md` (historical snapshots — preserve as-is).
- `docs/project/versions/**/CHANGELOG.md` (CHANGELOG has its own format).
- Repo-root `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`.

### Field semantics

| Field | Required | Notes |
|---|---|---|
| `title` | yes | Title-case human label. Need not match the H1 verbatim. |
| `status` | yes | One of the five enum values below. Never invent new values. |
| `version` | yes | `backend@x.y.z, frontend@x.y.z`, or `n/a` for non-feature docs. |
| `last_updated` | yes | ISO `YYYY-MM-DD`. Bump every time you change the body. |
| `owner` | yes | This repo: always `maintainer`. |
| `related_paths` | yes | Repo-relative paths the doc describes. ≥ 1 entry. |

## 3. Status Enum

```
draft        — under active drafting, not implemented
planning     — design approved, no code yet
in-progress  — implementation underway, doc may diverge from code
shipped      — code is in production / merged; doc reflects current behavior
superseded   — replaced by another doc (link to successor in body)
```

Anything else is invalid. Do NOT use `Implemented`, `Deployed`, `Completed`,
`Done`, emoji status badges, or inline `> **Status**: ...` blocks — those legacy
formats are explicitly retired.

## 4. Dates

- All dates: ISO `YYYY-MM-DD`. No US `MM/DD/YYYY`, no Chinese `2026年5月`.
- `last_updated` is mandatory on every frontmatter-bearing file.

## 5. Internal Links

- **Relative paths only.** Never embed absolute paths like `D:\repo\...` or
  `file:///` URLs. Treat the doc as if it would be read on GitHub.
- Use markdown link form `[text](relative/path.md)`. Avoid bare URLs for
  internal targets.
- When you move or rename a doc, run a repo-wide grep for the old path and
  fix every backlink in the same commit.

## 6. Code Blocks

- Always tag the language: `bash`, `python`, `typescript`, `tsx`, `json`,
  `yaml`, `mermaid`, `text`.
- Untagged fences are reserved for inline ASCII diagrams.

## 7. Adding a New Feature

When you add a feature, in the same change set:

1. Create `docs/features/<feature-name>.md` with frontmatter (`status: planning`
   or `in-progress`).
2. Link it from `docs/README.md` and `docs/features/README.md`.
3. As the feature ships, bump `status: shipped`, fill `version:`, and update
   `last_updated`.
4. If the feature replaces an older doc, set the old doc's `status: superseded`
   and link to the new one from its body.

## 8. Editing an Existing Doc

- Bump `last_updated`.
- If behavior changed materially, update `version:`.
- Keep changes scoped — do not silently rewrite history. If the doc no longer
  reflects current code, prefer marking it `superseded` and creating a new doc
  over a stealth rewrite.

## 9. Case Study Template

Files under `docs/case-studies/` follow this structure:

```markdown
---
title: <short title>
status: shipped       # case studies describe past events; use shipped or superseded
version: n/a
last_updated: YYYY-MM-DD
owner: maintainer
related_paths:
  - <path that was the root cause>
---

# <Title>

> **TL;DR (EN)**: 2–3 sentences in English.
> **TL;DR (中文)**: 2–3 句中文摘要。

## 1. Context
What was the situation, what triggered the investigation.

## 2. Investigation
Hypotheses tried, dead ends, what surprised you.

## 3. Root Cause
The actual mechanism.

## 4. Fix
What we changed and why.

## 5. Lessons
Generalizable takeaways.
```

The body language is the author's choice (Chinese is fine), but the TL;DR
**must** be bilingual so an outside reader can decide whether to keep reading.

## 10. Versions & CHANGELOG

- Backend and frontend version independently. See
  [docs/project/versions/README.md](../project/versions/README.md).
- `CHANGELOG.md` is append-only per component. Do not rewrite history.
- When a feature is removed (e.g. during fork-to-personal-local migration),
  delete the section describing that feature outright; do not leave dangling
  entries that reference deleted code.

## 11. Validation Hooks (informal)

Before committing docs-only changes, sanity-check:

```bash
# All frontmatter files start with ---
for f in docs/features/*.md docs/development/*.md \
         docs/architecture/*.md docs/case-studies/*.md; do
  [[ "$f" == */README.md ]] && continue
  head -1 "$f" | grep -q '^---$' || echo "MISSING FRONTMATTER: $f"
done

# No retired status values
grep -hE '^status:' docs/features/*.md docs/development/*.md \
                    docs/architecture/*.md docs/case-studies/*.md \
  | grep -vE 'status: (draft|planning|in-progress|shipped|superseded)' \
  && echo "INVALID STATUS"

# No absolute Windows paths in docs
grep -rn 'D:\\repo' docs/ && echo "ABSOLUTE PATH LEAK"
```

## 12. What This Doc Does NOT Cover

- Generated API docs (we read OpenAPI live from
  `http://localhost:8000/openapi.json` — see
  [architecture/api-reference.md](../architecture/api-reference.md)).
- Inline code docstrings — see
  [coding-standards.md](coding-standards.md).
- `backend/src/agent/skills/*/SKILL.md` — those are runtime-loaded by the agent
  and have their own format requirements; **do not** apply this frontmatter
  schema to them. See
  [../../backend/src/agent/skills/README.md](../../backend/src/agent/skills/README.md)
  for the skill catalog.
