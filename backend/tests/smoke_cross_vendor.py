"""
Cross-vendor smoke test: verify every per-role LLM in MODELS can do
(1) basic chat, (2) tool-calling — both the surfaces Deep ReAct depends on.

Run from backend/:
    python -m tests.smoke_cross_vendor
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback

os.environ.setdefault("MAESTRO_BASE_URL", "http://localhost:23333/api/anthropic")

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agent.llm_factory import MODELS, get_llm  # noqa: E402


@tool
def get_stock_price(symbol: str) -> str:
    """Get the current stock price for a symbol."""
    return f"{symbol}: $123.45"


async def probe(role: str, model_id: str) -> dict:
    result = {"role": role, "model": model_id, "chat": "?", "tools": "?", "err": ""}
    try:
        llm = get_llm(role, max_tokens=200, timeout=30)
    except Exception as e:
        result["err"] = f"factory: {e}"
        return result

    try:
        r = await llm.ainvoke([HumanMessage(content="reply with exactly: ok")])
        text = (
            (r.content if isinstance(r.content, str) else str(r.content))
            .strip()
            .lower()
        )
        result["chat"] = "OK" if "ok" in text else f"WEIRD({text[:40]})"
    except Exception as e:
        result["chat"] = "FAIL"
        result["err"] = f"chat: {type(e).__name__}: {str(e)[:200]}"
        return result

    try:
        bound = llm.bind_tools([get_stock_price])
        r = await bound.ainvoke(
            [HumanMessage(content="What is the price of AAPL? Use the tool.")]
        )
        tc = getattr(r, "tool_calls", None) or []
        result["tools"] = f"OK({len(tc)} call)" if tc else "NO_CALL"
    except Exception as e:
        result["tools"] = "FAIL"
        result["err"] = f"tools: {type(e).__name__}: {str(e)[:200]}"

    return result


async def main():
    print(f"{'role':<22} {'model':<28} {'chat':<8} {'tools':<14} err")
    print("-" * 110)
    seen = {}
    for role, model in MODELS.items():
        if model in seen:
            print(f"{role:<22} {model:<28} (dup of {seen[model]})")
            continue
        seen[model] = role
        r = await probe(role, model)
        print(
            f"{r['role']:<22} {r['model']:<28} {r['chat']:<8} {r['tools']:<14} {r['err']}"
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
