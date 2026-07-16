---
title: The 12-Factor Agent Playbook
status: shipped
version: backend@0.33.0
last_updated: 2026-07-16
owner: maintainer
related_paths:
  - backend/src/agent/
---

# The 12-Factor Agent Playbook

This guide applies 12-Factor principles to the current hybrid system. LangGraph
is used where a tool loop or explicit research graph adds value; deterministic
services and direct chat are not forced into graphs.

## Executive Summary

1. **Adopt the Philosophy**: Start with the 12-Factor Agent principles as your architectural North Star.
2. **Instrument First**: Use `structlog` structured logs from day one for observability. Don't fly blind.
3. **Design for Control**: Use explicit Python orchestration, deterministic
   services, or LangGraph according to the workflow lifecycle.
4. **Build Small, Compose Big**: Create small, specialized tools and agents using **LCEL** and orchestrate them within your LangGraph.
5. **Deploy as a Stateless Service**: Wrap your agent in a standard API to make it triggerable and scalable.

## Phase 1: Foundation & Tooling

This is the setup phase where you establish the principles and tools for your project.

### 1. Adopt the 12-Factor Mindset
Before writing any code, internalize the core principles. Your goal is not to build a single, magical prompt, but a robust software system. Key tenets: own your prompts, manage state explicitly, and build small, composable units.

### 2. Instrument Everything (Factor 9: Error Handling)
This is your first and most critical step.
- **Action**: Emit `structlog` JSON logs with consistent context fields (`user_id`, `chat_id`, `symbol`, `tool_name`, latency) at every node entry/exit, tool call, and error.
- **Why**: You gain immediate, transparent visibility into every step of your agent. Debugging is no longer guesswork — you can grep / `jq` the logs to see exact inputs/outputs, latencies, and errors for every component, which is essential for handling failures gracefully.

### 3. Manage Prompts as Code (Factor 2: Own Your Prompts)
- **Action**: Version control your prompts as code files or configuration alongside the agent. Treat prompt changes as code changes that require a version bump.
- **Why**: This treats prompts as first-class assets. They can be versioned, tested, and updated independently of the surrounding plumbing, promoting iteration.

## Phase 2: Architecture & Design

This is where you design the skeleton of your agent using modern LangChain tools.

### 4. Choose Explicit Control Flow (Factor 8: Own Your Control Flow)
- **Action**: Use LangGraph for the ReAct tool loop and Deep Research state
  graph, and ordinary typed Python for deterministic portfolio and API
  orchestration.
- **Why**: The implementation mechanism should match the lifecycle. A graph is
  useful for iterative or resumable transitions, but unnecessary graph nodes
  make deterministic logic harder to test.

### 5. Define an Authoritative State Owner (Factor 5: Unify State)
- **Action**: MongoDB owns conversational messages and compacted summaries.
  Per-request ReAct graph state is transient. Future Research Job checkpoints
  will own only resumable research execution state.
- **Why**: One explicit owner prevents Mongo history from being duplicated with
  an unrelated graph checkpointer.

### 6. Build Small, Composable Tools (Factor 10: Small Agents)
- **Action**: For each node in your graph that performs an action, build a small, self-contained chain using **LCEL (`|`)**. This chain might be a RAG pipeline, a tool-calling function, or a simple prompt-LLM call.
- **Why**: This makes your system modular and testable. You can develop and debug each tool in isolation before composing them in the main graph.

## Phase 3: Implementation & Deployment

This is the development loop where you bring the architecture to life.

### 7. Plan for Interrupts (Factor 6 & 7: Pause/Resume & Human-in-the-Loop)
- **Action**: Explicitly design nodes in your graph that represent "wait" states. For example, add an edge that transitions to a `waitForHumanApproval` node.
- **Why**: LangGraph's state-driven design is perfect for this. You can persist the state, wait for an external event (like a human clicking a button in a UI), and then resume the graph's execution with the new information added to the state.

### 8. Code the Control Flow (Factor 8, again)
- **Action**: Implement the logic of your agent using LangGraph's conditional edges. The function governing an edge should inspect the current state and decide which node to visit next.
- **Why**: This is the programmatic implementation of your explicit control flow. `if state['tool_error_count'] > 2: return "human_review_node"`.

### 9. Deploy as a Stateless API (Factor 11 & 12: Triggerable & Stateless)
- **Action**: Wrap your LangGraph agent in a web server like FastAPI. Create an endpoint that accepts an input (e.g., `user_id`, `message`).
- **Why**: This makes your agent a standard, stateless web service. For a given request, you can load the relevant state from a database, run it through your LangGraph "reducer", and save the new state. The server itself holds no memory between requests, making it easy to scale horizontally.
