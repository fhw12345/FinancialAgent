"""Recorded Chat Completions envelopes; no real account material."""

import json
import httpx


def chat_sse(deltas, *, finish="stop", usage=True):
    events = [
        {"choices": [{"index": 0, "delta": delta, "finish_reason": None}]}
        for delta in deltas
    ]
    events.append({"choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
    if usage:
        events.append(
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 8,
                    "prompt_tokens_details": {"cached_tokens": 3},
                },
            }
        )
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content="".join(
            "data: " + json.dumps(e, ensure_ascii=False) + "\n\n" for e in events
        )
        + "data: [DONE]\n\n",
    )


def chat_tool(name, arguments):
    return chat_sse(
        [
            {
                "reasoning_details": [
                    {
                        "type": "reasoning.encrypted",
                        "id": "r1",
                        "data": "opaque-recorded",
                    }
                ]
            },
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "chat_call_1",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)},
                    }
                ]
            },
        ],
        finish="tool_calls",
    )
