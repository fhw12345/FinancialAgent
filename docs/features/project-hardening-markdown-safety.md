---
title: Untrusted Agent Markdown Rendering Safety
status: in-progress
version: frontend@0.32.5
last_updated: 2026-09-09
owner: maintainer
related_paths:
  - frontend/src/components/chat/ChatMessages.tsx
  - frontend/src/components/chat/__tests__/
  - frontend/e2e/
---

# PH-005: Untrusted Agent Markdown Rendering Safety

## Objective

Treat all assistant, tool, news, and research content as untrusted and prevent
raw HTML or active embeds from crossing the LLM-to-browser trust boundary while
preserving supported Markdown.

## Rendering Contract

Supported: headings, paragraphs, lists, tables, links, blockquotes, fenced code,
and inline code. Unsupported content must render as text or be removed:

- scripts and event handlers;
- iframe, object, embed, form, style, and meta elements;
- unsafe URL schemes;
- arbitrary SVG/MathML active content;
- remote images unless explicitly approved.

## Ownership and Parallel Safety

Agent E owns `ChatMessages.tsx` rendering configuration and security tests.
Coordinate with PH-006 before changing shared stream/message types. PH-009 moves
components only after this task merges.

## Implementation Plan

1. Prefer removing `rehypeRaw` if no accepted content requires HTML.
2. Otherwise add `rehype-sanitize` with an explicit minimal schema.
3. Add a safe link renderer using `rel="noopener noreferrer"` and appropriate
   target behavior.
4. Decide and document image policy.
5. Add a defense-in-depth CSP compatible with Vite local development if in
   scope; otherwise create a follow-up with an explicit rationale.
6. Test historical assistant messages to avoid display regressions.

## Test Plan

### Component tests

Render payloads containing scripts, `onerror`, iframe, forms, SVG links,
`javascript:` URLs, data URLs, and ordinary GFM. Assert dangerous nodes and
attributes are absent and normal Markdown remains visible.

### Playwright E2E — required

Scenario `ph-005-untrusted-markdown`:

1. Use a deterministic chat backend that streams an assistant response
   containing malicious raw HTML plus normal Markdown.
2. Assert no iframe/form/script/active embed exists.
3. Assert no unexpected network request is made.
4. Assert headings, table, code, and safe HTTPS link render correctly.
5. Capture `docs/features/assets/ph-005/01-sanitized-agent-markdown.png`.

A second assertion must click the safe link or inspect its attributes and prove
opener isolation. No actual malicious external domain should be contacted.

## Acceptance Criteria

- [ ] Raw untrusted HTML cannot create active DOM content.
- [ ] Unsafe URL schemes are rejected.
- [ ] Supported GFM display remains intact.
- [ ] Component security corpus passes.
- [ ] Browser test proves malicious content is inert.
- [ ] Screenshot and deterministic fixture details are recorded.
- [ ] Frontend full suite, lint, type-check, and build pass.

## 2026-09-09 Closeout Review

The previous corpus tested HTML images only. Markdown image syntax still creates
`img` elements and remote requests, so PH-005 cannot be closed from the previous
screenshot. Add a failing regression for Markdown images and unsafe link schemes,
then disallow images explicitly. Extract only the existing Markdown renderer
configuration to keep the touched source under 500 lines; this is a narrow
security-boundary change, not the PH-009 decomposition program.

Test English/Chinese historical output, normal GFM, fenced code, forms, SVG,
MathML, event handlers, `javascript:`/`data:` links, and Markdown images. Browser
requests to the fixture attacker domain must be blocked and counted, never sent.
CSP is deferred: Vite HMR requires development-specific connect/script policy;
removing HTML parsing plus explicit image rejection is the boundary for this
change. A static-serving CSP should be designed with the eventual runtime server.

## Implementation and Test Record

Removed `rehypeRaw` from assistant rendering and added isolated external-link
attributes. The component security test proves script, iframe, and image HTML
remain inert while headings, GFM tables, and safe links render.

Playwright scenario `untrusted assistant HTML stays inert` streamed a
deterministic malicious assistant fixture, asserted zero active elements and
zero attacker-domain requests, then captured
[`assets/ph-005/01-sanitized-agent-markdown.png`](assets/ph-005/01-sanitized-agent-markdown.png).
The tested implementation commit is `960d29a`.

## Current Validation — 2026-09-09 (Unpublished)

Tested implementation: `db1e4b8739c21fb160e6eadda65dab53617522aa`, frontend `0.32.5`.
The Markdown-image regression failed before the fix and passed after it.
The six-case component corpus passes. Screenshot review additionally exposed
fenced-code text matching its inherited background; a failing browser contrast
assertion preceded the scoped `pre code` CSS repair. `AssistantMarkdown.tsx` owns the unchanged
GFM styles and explicit `img` rejection; `ChatMessages.tsx` is now 406 lines.

The browser corpus includes Markdown tracking images, HTML forms/SVG, unsafe
links and fenced code. Attacker requests are intercepted and aborted if any
occur; the passing assertion observes zero. Safe links retain opener isolation.
The refreshed [screenshot](assets/ph-005/01-sanitized-agent-markdown.png) shows the
supported content after the safety assertions.

Frontend validation: 254 tests, zero production warnings, 131 total test/E2E
warnings, successful type-check and build. Windows denied deleting the old mounted
`dist/assets`; a fresh `/tmp/ph-hardening-dist` output passed as non-root.
The fix and evidence are committed and pushed on `hardening/closeout-ci`.
Hosted PR/CI and merge are pending, so status stays in progress.

## Risks

Sanitization can change old assistant output. Validate representative English
and Chinese histories and document intentional rendering differences instead
of widening the allowlist without a security review.
