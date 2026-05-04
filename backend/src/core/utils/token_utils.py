"""
Token usage extraction utilities for LangChain messages.

Handles multiple message formats from different LLM providers (DashScope, OpenAI, etc.).
"""

from typing import Any


def extract_token_usage_from_messages(messages: list[Any]) -> tuple[int, int, int]:
    """
    Extract total token usage from LangChain messages.

    Supports multiple metadata formats:
    - usage_metadata (newer LangChain format)
    - response_metadata.token_usage (DashScope/Tongyi format)
    - response_metadata.usage (OpenAI format)

    Args:
        messages: List of LangChain message objects (AIMessage, HumanMessage, etc.)

    Returns:
        Tuple of (input_tokens, output_tokens, total_tokens)

    Example:
        >>> from langchain_core.messages import AIMessage
        >>> messages = [AIMessage(content="Hello", usage_metadata={"input_tokens": 10, "output_tokens": 5})]
        >>> extract_token_usage_from_messages(messages)
        (10, 5, 15)
    """
    total_input_tokens = 0
    total_output_tokens = 0

    for msg in messages:
        # Only process AIMessage (responses from LLM)
        if msg.__class__.__name__ != "AIMessage":
            continue

        # Try usage_metadata first (newer LangChain format — a dict, not an object)
        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            um = msg.usage_metadata
            total_input_tokens += um.get("input_tokens", 0)
            total_output_tokens += um.get("output_tokens", 0)

        # Fallback to response_metadata (provider-specific formats)
        elif hasattr(msg, "response_metadata") and msg.response_metadata:
            # Try DashScope/Tongyi format first (token_usage)
            # Then OpenAI format (usage)
            usage = msg.response_metadata.get(
                "token_usage"
            ) or msg.response_metadata.get("usage", {})

            # DashScope uses input_tokens/output_tokens
            # OpenAI uses prompt_tokens/completion_tokens
            total_input_tokens += usage.get("input_tokens", 0) or usage.get(
                "prompt_tokens", 0
            )
            total_output_tokens += usage.get("output_tokens", 0) or usage.get(
                "completion_tokens", 0
            )

    total_tokens = total_input_tokens + total_output_tokens

    return total_input_tokens, total_output_tokens, total_tokens


def extract_token_usage_from_agent_result(
    agent_result: dict[str, Any],
) -> dict[str, int]:
    """
    Extract token usage from agent invocation result.

    Args:
        agent_result: Result dictionary from agent.ainvoke() or similar

    Returns:
        Dictionary with keys: input_tokens, output_tokens, total_tokens
        Returns zeros if no token usage found.

    Example:
        >>> result = {"messages": [...], "input_tokens": 100, "output_tokens": 50}
        >>> extract_token_usage_from_agent_result(result)
        {'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150}
    """
    input_tokens = agent_result.get("input_tokens", 0)
    output_tokens = agent_result.get("output_tokens", 0)
    total_tokens = agent_result.get("total_tokens", 0)

    # If total_tokens not provided, calculate it
    if total_tokens == 0 and (input_tokens > 0 or output_tokens > 0):
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
