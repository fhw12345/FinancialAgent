"""Probe how each vendor reports token usage via Maestro."""

from __future__ import annotations

import asyncio
import os
import sys

os.environ.setdefault("MAESTRO_BASE_URL", "http://localhost:23333/api/anthropic")
os.environ.setdefault("MAESTRO_AUTH_TOKEN", "Powered by Agent Maestro")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.messages import HumanMessage  # noqa: E402

from src.agent.llm_factory import get_llm  # noqa: E402


async def probe(role: str):
    llm = get_llm(role, max_tokens=50, timeout=30)
    r = await llm.ainvoke([HumanMessage(content="say hi")])
    print(f"\n=== {role} ===")
    print(f"  type(usage_metadata) = {type(r.usage_metadata).__name__}")
    print(f"  usage_metadata = {r.usage_metadata}")
    print(f"  response_metadata keys = {list(r.response_metadata.keys())}")
    if "token_usage" in r.response_metadata:
        print(
            f"  response_metadata['token_usage'] = {r.response_metadata['token_usage']}"
        )
    if "usage" in r.response_metadata:
        print(f"  response_metadata['usage'] = {r.response_metadata['usage']}")


async def main():
    for role in ["deep_planner", "sub_financial", "sub_news"]:
        try:
            await probe(role)
        except Exception as e:
            print(f"\n=== {role} === FAIL: {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
