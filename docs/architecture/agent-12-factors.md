---
title: The 12-Factor Agent Playbook
status: shipped
version: n/a
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/src/agent/
---

# The 12-Factor Agent Playbook

This guide synthesizes the 12-Factor philosophy with modern LangChain tools (LangGraph, LCEL) to create reliable, observable, and scalable AI agents.

## Executive Summary

1. **Adopt the Philosophy**: Start with the 12-Factor Agent principles as your architectural North Star.
2. **Instrument First**: Use `structlog` structured logs from day one for observability. Don't fly blind.
3. **Design for Control**: Use **LangGraph** to define an explicit state machine, not a single LLM loop. You own the control flow.
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

### 4. Design as a Graph, Not a Loop (Factor 8: Own Your Control Flow)
- **Action**: Choose **LangGraph** as your core architecture. Sketch out your agent's logic as a state diagram with nodes (steps) and edges (transitions).
- **Why**: This forces you to define the agent's behavior explicitly. You decide the possible paths of execution, rather than letting the LLM dictate the flow, which is the primary cause of unreliable agent behavior.

### 5. Define a Unified State Object (Factor 5: Unify State)
- **Action**: Create a typed data class (e.g., using Pydantic) that represents the entire state of your graph. This object will be passed between every node.
- **Why**: This creates a single, predictable source of truth. The state should contain everything: message history, intermediate results, user information, and error counts. Each node's job is to read from and update this state object.

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
