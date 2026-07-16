"""Normalize LangChain message content into user-visible text."""

from typing import Any


def message_content_to_text(content: Any) -> str:
    """Extract text from string or structured LangChain content blocks."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                continue
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(part for part in parts if part)
    return str(content)
