"""Deterministic Anthropic-compatible stub for browser conversation tests."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
_requests: list[dict[str, Any]] = []
_CODEWORD_RE = re.compile(r"\b[A-Z]+-\d+\b")


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
    return str(content)


def _response_text(payload: dict[str, Any]) -> str:
    messages = payload.get("messages") or []
    user_texts = [
        _message_text(message) for message in messages if message.get("role") == "user"
    ]
    latest = user_texts[-1] if user_texts else ""
    latest_lower = latest.lower()
    system = payload.get("system") or ""

    if "professional financial-translation engine" in system:
        passages = re.split(r"\n(?=\d+\.\s)", latest)
        translated = [
            re.sub(r"^\d+\.\s*", "", passage).strip()
            for passage in passages
            if passage.strip()
        ]
        return "\n<<<TRANSLATION_SEPARATOR>>>\n".join(translated)

    codewords = [
        match.group(0)
        for text in user_texts[:-1]
        for match in _CODEWORD_RE.finditer(text)
    ]

    if "backend restart" in latest_lower:
        return (
            f"After restart, the codeword is still {codewords[-1]}."
            if codewords
            else "No prior codeword was found after restart."
        )
    if "remember" in latest_lower:
        current = _CODEWORD_RE.search(latest)
        return f"Acknowledged {current.group(0)}." if current else "Acknowledged."
    if "exact codeword" in latest_lower:
        return (
            f"The exact codeword is {codewords[-1]}."
            if codewords
            else "No prior codeword was found."
        )
    return "Acknowledged."


def _message_payload(text: str) -> dict[str, Any]:
    return {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "model": "e2e-model",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": max(1, len(text) // 4)},
    }


async def _stream_events(text: str) -> AsyncIterator[str]:
    message = _message_payload(text)
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {**message, "content": [], "stop_reason": None},
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            },
        ),
        (
            "content_block_stop",
            {"type": "content_block_stop", "index": 0},
        ),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": message["usage"],
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    for event_name, data in events:
        yield f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


@app.post("/v1/messages")
async def messages(request: Request):
    payload = await request.json()
    _requests.append(payload)
    text = _response_text(payload)
    if payload.get("stream"):
        return StreamingResponse(
            _stream_events(text),
            media_type="text/event-stream",
        )
    return JSONResponse(_message_payload(text))


@app.get("/requests")
async def requests():
    return {"requests": _requests}


@app.delete("/requests")
async def clear_requests():
    _requests.clear()
    return {"cleared": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
