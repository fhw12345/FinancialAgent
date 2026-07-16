"""Tests for LangChain structured message-content normalization."""

from types import SimpleNamespace

from src.core.utils.message_content import message_content_to_text


def test_string_content_is_preserved():
    assert message_content_to_text("answer") == "answer"


def test_text_blocks_are_joined_and_non_text_blocks_ignored():
    content = [
        {"type": "thinking", "thinking": "private reasoning"},
        {"type": "text", "text": "First paragraph."},
        {"type": "tool_use", "name": "quote"},
        {"type": "text", "text": "Second paragraph."},
    ]

    assert message_content_to_text(content) == "First paragraph.\nSecond paragraph."


def test_object_text_blocks_are_supported():
    content = [SimpleNamespace(text="One"), SimpleNamespace(text="Two")]

    assert message_content_to_text(content) == "One\nTwo"
