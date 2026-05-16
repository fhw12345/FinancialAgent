# Case Studies

Real-world debugging walkthroughs and design-decision write-ups from this
project. Each case follows: **Context → Investigation → Root Cause → Fix →
Lessons**. The emphasis is on the *thinking process* — the hypotheses tried,
the dead ends, the moment the mental model of the system finally matched
reality — not just the final patch.

Every entry starts with a bilingual **TL;DR (EN / 中文)** so an outside reader
can decide whether the case is relevant before reading the Chinese body.

## Index

| Date | Title | Stack | Topic |
|------|-------|-------|-------|
| 2026-05-04 | [Ghost Compose Project](2026-05-04-ghost-compose-project.md) | Docker | Compose-project name collision + silent empty bind mount on Windows |
| 2026-05-04 | [Token Count Always Zero](2026-05-04-token-extraction-getattr-on-dict.md) | LangChain / tests | `getattr` on a dict silently returns the default; `Mock` hid the real shape |
| 2026-05-04 | [Finnhub Fallback Chain](2026-05-04-finnhub-fallback-chain.md) | Service architecture | Three-tier fallback; "lying comments"; mock-coverage blind spots |
| 2026-05-04 | [Decision Tracking Cross-Layer](2026-05-04-decision-tracking-cross-layer.md) | End-to-end | Five-layer instrumentation; the "which container am I talking to?" port trap (recurring) |
| 2026-05-05 | [Translation Pipeline Multi-Layer](2026-05-05-translation-pipeline-multilayer.md) | Frontend i18n + LLM | React Query cache hit vs `isLoading` divergence; `max_tokens` silent truncation; raw markdown bleed |
| 2026-05-05 | [SELL = "Close Long" Prompt Semantics](2026-05-05-sell-close-long-prompt-semantics.md) | LLM prompt design | BUY/SELL share schema fields with inverted semantics; reasoning citation is ambiguous |
| 2026-05-06 | [Vite + Docker HMR Silent Failure](2026-05-06-vite-docker-hmr-silent-failure.md) | Vite / Docker / inotify | Windows bind mount propagates content but not inotify events; habits masked the bug for weeks |
| 2026-05-09 | [SEC EDGAR Form 4 URL Resolution](2026-05-09-sec-edgar-form4-url-resolution.md) | SEC integration | Unit tests with mocked transports passed; real SEC paths returned 404; integration tests revealed the URL-transformation bug |

## Why This Exists

Most "war story" posts present a clean three-act narrative (problem →
investigation → fix). The cases in this directory keep the messy parts on
purpose: the wrong hypotheses tested first, the moments of "wait, is the
comment lying?", the times the test mocks did not match the real data shape.
That mess is the actual training signal — both for the maintainer revisiting
the code six months later and for any reader trying to learn how to debug
similar systems.
