---
title: Markdown and Machine Decisions Could Diverge
status: shipped
version: backend@0.48.0, frontend@0.28.1
last_updated: 2026-07-28
owner: maintainer
related_paths:
  - backend/src/agent/debate_types.py
  - backend/src/agent/deep_workflow.py
  - backend/src/api/chat/streaming/lifecycle.py
  - backend/src/api/chat/streaming/deep_verdict_persistence.py
  - backend/src/database/repositories/portfolio_order_repository.py
---

# Markdown and Machine Decisions Could Diverge

> **TL;DR (EN)**: A structured verdict could persist BUY while its independent
> Markdown report told the user SELL. The verdict schema now validates the
> displayed Action against the machine field, requires complete concern
> assessments, and persists its signal only after durable chat completion.
>
> **TL;DR (中文)**：structured verdict 可能持久化 BUY，但独立 Markdown 却向
> 用户显示 SELL。现在 schema 会校验显示 Action 与机器字段一致，确保每个
> concern 都被评估，并且只在聊天与 run 持久化成功后写入 signal。

## 1. Context

Deep Research originally treated the final Markdown report as the source for
both the user-facing answer and downstream portfolio signal extraction.
Debate concerns and rebuttals were also recovered from free-form output with
regex and code-fence parsing.

This made the workflow appear structured while important machine decisions
still depended on text formatting.

## 2. Investigation

Replacing regex parsing with Pydantic exposed several less obvious boundaries:

- two debate rounds commonly reused IDs such as `C1`;
- a rebuttal could return a valid but unrelated concern ID;
- a verdict could omit assessments while still passing its base schema;
- Markdown could contain multiple, qualified, or negated action values;
- a signal could be written before the terminal assistant message became
  durable;
- cancellation could interrupt persistence between a committed run and its
  signal.

The browser path also had to prove that the structured verdict survived
MongoDB persistence and the reload API, not only that backend models parsed.

## 3. Root Cause

The workflow had multiple independent representations of one decision:

1. free-form debate text;
2. parsed concern and rebuttal dictionaries;
3. final Markdown;
4. structured verdict metadata;
5. a portfolio signal row.

There was no single invariant connecting all five representations or defining
their persistence order.

## 4. Fix

- Require one strict JSON object for concerns and rebuttals.
- Namespace concern IDs by round and validate exact rebuttal coverage.
- Require one verdict assessment for every concern.
- Accept documented Markdown Action or Recommendation fields only when their
  value is exactly one unqualified enum matching the structured action.
- Store the complete verdict in terminal assistant metadata.
- Run signal persistence from a durable lifecycle hook after message/run
  completion and before title/event I/O.
- Shield committed transitions and signal persistence through cancellation.
- Use deterministic full-entropy message IDs and atomic order upserts.

## 5. Lessons

- Structured metadata and user-visible prose are two representations of one
  decision; equality must be enforced, not assumed.
- IDs generated independently by an LLM need workflow-owned namespaces.
- Validation includes completeness and referential integrity, not only field
  types.
- Side effects derived from a result belong after the authoritative durable
  transition.
- Cancellation tests must cover the moment after a database commit but before
  the awaiting coroutine resumes.
