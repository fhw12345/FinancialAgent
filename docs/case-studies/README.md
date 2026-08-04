# Case Studies

Real-world debugging walkthroughs and design-decision write-ups from this
project. Each case follows: **Context → Investigation → Root Cause → Fix →
Lessons**. The emphasis is on the _thinking process_ — the hypotheses tried,
the dead ends, the moment the mental model of the system finally matched
reality — not just the final patch.

Every entry starts with a bilingual **TL;DR (EN / 中文)** so an outside reader
can decide whether the case is relevant before reading the Chinese body.

## Index

| Date       | Title                                                                                       | Stack                   | Topic                                                                                                                        |
| ---------- | ------------------------------------------------------------------------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 2026-08-04 | [A Green Eval Can Still Be Fiction](2026-08-04-a-green-eval-can-still-be-fiction.md) | Python / LangGraph / FastAPI / React | Production Prompt/tool/Judge evaluation, hard cost budgets, paid-failure accounting, and persistent browser evidence |
| 2026-08-03 | [Aggregate Gates Can Hide Router Gaps](2026-08-03-aggregate-gates-can-hide-router-gaps.md) | Python / FastAPI / React / Playwright | Versioned eval gates exposed concept, Deep Research, and Chinese ticker-boundary routing gaps before shipment |
| 2026-07-30 | [A Data Refetch Recreated the Entire Chart](2026-07-30-data-refetch-recreated-chart.md) | React Query / Lightweight Charts / Playwright | Preserving one chart instance while synchronizing price, volume, ranges, intervals, and exact tooltip data |
| 2026-07-28 | [Date Ranges Need Provider Contracts](2026-07-28-date-ranges-need-provider-contracts.md) | React / FastAPI / yfinance / Redis / Playwright | End-to-end date range semantics across provider limits, caches, timezones, analysis, and persistence |
| 2026-07-27 | [Markdown and Machine Decisions Could Diverge](2026-07-27-markdown-and-machine-decisions-diverged.md) | Pydantic / LangGraph / Playwright | Strict debate JSON and consistency between displayed and persisted verdict actions |
| 2026-07-27 | [Backend Tests Are Not Browser Evidence](2026-07-27-backend-tests-are-not-browser-evidence.md) | Playwright / Workflow / Documentation | Reopening shipped work to restore mandatory browser evidence |
| 2026-07-27 | [Large Prompts Need Builders](2026-07-27-large-prompts-need-builders.md) | Portfolio / Prompt Registry / Pydantic | Exact prompt extraction, source-test migration, and file-size boundaries |
| 2026-07-27 | [Skipped Prompts Are Not Used Prompts](2026-07-27-skipped-prompts-are-not-used-prompts.md) | Portfolio / Pydantic / Prompt Registry | Conditional prompt execution and truthful usage metadata |
| 2026-07-27 | [Prompt Observability Must Survive Failure](2026-07-27-prompt-observability-must-survive-failure.md) | LangGraph / Prompt Registry / asyncio | Conditional prompt usage across success, failure, timeout, and cancellation |
| 2026-07-27 | [Singleton Prompt Metadata Crossed Requests](2026-07-27-singleton-prompt-metadata-race.md) | asyncio / Prompt Registry / MongoDB | Request-local prompt usage and concurrency-safe durable metadata |
| 2026-07-21 | [A Prompt Registry Can Lie](2026-07-21-a-registry-can-lie.md) | Prompt / Pydantic / Evaluation | Runtime-linked versions, structured router output, and honest coverage metadata |
| 2026-07-21 | [The First Golden Suite Found Router Gaps](2026-07-21-evaluation-first-found-router-gaps.md) | Python / Router / Pydantic | Honest deterministic baselines, no-live guarantees, and real symbol-safety evaluation |
| 2026-07-21 | [One Logical Request Could Start Two Expensive Runs](2026-07-21-one-click-two-expensive-runs.md) | MongoDB / SSE / React | Atomic request claims, terminal replay, and run-versus-stream identity |
| 2026-07-21 | [One Stream Had Many Event Shapes](2026-07-21-one-stream-many-event-shapes.md) | SSE / FastAPI / React / Playwright | Run-wide sequencing, canonical envelopes, compatibility adapters, and cleanup races |
| 2026-07-20 | [Three Chat Handlers Had Three Lifecycles](2026-07-20-three-chat-handlers-three-lifecycles.md) | asyncio / SSE / MongoDB / React | Shared lifecycle ownership, event ordering, terminal compensation, and late transport races |
| 2026-07-20 | [One Run Model Had to Survive Four Lifecycles](2026-07-20-one-run-model-four-lifecycles.md) | MongoDB / SSE / asyncio / React | Atomic run state, stream closure, leased compatibility keys, and migration recovery |
| 2026-07-17 | [A Typewriter Effect Was Reported as Model Streaming](2026-07-17-typewriter-effect-was-not-streaming.md) | SSE / LLM / React / Playwright | Real model tokens versus buffered response delivery and truthful latency metrics |
| 2026-07-17 | [Stop Closed the Stream but Left the Agent Running](2026-07-17-stop-button-left-agent-running.md) | asyncio / SSE / React Query / Playwright | Abort propagation, awaited task cancellation, and idempotent cancelled terminal state |
| 2026-07-17 | [Watchlist Analysis Updated the Wrong Collection](2026-07-17-watchlist-analysis-wrong-collection.md) | FastAPI / MongoDB / React Query / Playwright | Collection mismatch was hidden as success; canonical repository wiring and real persistence proof |
| 2026-07-16 | [Deep Research Received History but Ignored It](2026-07-16-deep-research-lost-conversation-context.md) | LangGraph / MongoDB / Playwright | Structured prior thesis, horizon, risk, and constraints were added to every Deep graph node                           |
| 2026-07-16 | [Two Conversation State Owners Meant One Was Fictional](2026-07-16-mongo-conversation-state-authority.md) | MongoDB / LangGraph / Playwright | Removed decorative MemorySaver and proved continuity across backend restart                                         |
| 2026-07-16 | [Generic Chat Titles Hid Conversation Identity](2026-07-16-duplicate-chat-titles.md)        | MongoDB / FastAPI / UI context | Generic fallbacks and skipped update paths produced indistinguishable sidebar titles                                  |
| 2026-07-16 | [Structured LLM Content Blocks Reached a String Regex](2026-07-16-structured-content-block-list.md) | LangChain / SSE / Copilot Bridge | Final answer was a list of content blocks; title regex expected a string                                               |
| 2026-07-15 | [Deep Agent Silent Symbol Fallback](2026-07-15-deep-agent-silent-symbol-fallback.md)         | Agent / SSE / Playwright | Unresolved ticker silently became AAPL; typed clarification and real browser evidence                                        |
| 2026-07-15 | [Automatic Routing Exposed Windows Streaming Bugs](2026-07-15-auto-routing-windows-utf8.md) | FastAPI / SSE / Windows | Async-generator timeout misuse + cp1252 logging failure exposed by automatic v2 routing                                      |
| 2026-05-04 | [Ghost Compose Project](2026-05-04-ghost-compose-project.md)                                | Docker                  | Compose-project name collision + silent empty bind mount on Windows                                                          |
| 2026-05-04 | [Token Count Always Zero](2026-05-04-token-extraction-getattr-on-dict.md)                   | LangChain / tests       | `getattr` on a dict silently returns the default; `Mock` hid the real shape                                                  |
| 2026-05-04 | [Finnhub Fallback Chain](2026-05-04-finnhub-fallback-chain.md)                              | Service architecture    | Three-tier fallback; "lying comments"; mock-coverage blind spots                                                             |
| 2026-05-04 | [Decision Tracking Cross-Layer](2026-05-04-decision-tracking-cross-layer.md)                | End-to-end              | Five-layer instrumentation; the "which container am I talking to?" port trap (recurring)                                     |
| 2026-05-05 | [Translation Pipeline Multi-Layer](2026-05-05-translation-pipeline-multilayer.md)           | Frontend i18n + LLM     | React Query cache hit vs `isLoading` divergence; `max_tokens` silent truncation; raw markdown bleed                          |
| 2026-05-05 | [SELL = "Close Long" Prompt Semantics](2026-05-05-sell-close-long-prompt-semantics.md)      | LLM prompt design       | BUY/SELL share schema fields with inverted semantics; reasoning citation is ambiguous                                        |
| 2026-05-06 | [Vite + Docker HMR Silent Failure](2026-05-06-vite-docker-hmr-silent-failure.md)            | Vite / Docker / inotify | Windows bind mount propagates content but not inotify events; habits masked the bug for weeks                                |
| 2026-05-09 | [SEC EDGAR Form 4 URL Resolution](2026-05-09-sec-edgar-form4-url-resolution.md)             | SEC integration         | Unit tests with mocked transports passed; real SEC paths returned 404; integration tests revealed the URL-transformation bug |

## Why This Exists

Most "war story" posts present a clean three-act narrative (problem →
investigation → fix). The cases in this directory keep the messy parts on
purpose: the wrong hypotheses tested first, the moments of "wait, is the
comment lying?", the times the test mocks did not match the real data shape.
That mess is the actual training signal — both for the maintainer revisiting
the code six months later and for any reader trying to learn how to debug
similar systems.
