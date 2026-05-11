#!/usr/bin/env python3
"""Repair inverted `_zh` translations in MongoDB.

Background: a now-fixed bug had DashScope re-translate already-Chinese text
"to zh-CN", which the LLM interpreted as "translate to the other obvious
language" and emitted English. The English landed under `<field>_zh` while
the base field stayed Chinese. Symptom: frontend short-circuits on `_zh`
and shows English under a zh-CN UI.

Scope:
- portfolio_orders.metadata.full_research / full_research_zh
- messages.content / content_zh

For each row where `base` is mostly CJK and `<field>_zh` is mostly ASCII,
the base is already Chinese and the simplest fix is to copy base over the
bad _zh sibling. No LLM round-trip needed.

Also flushes Redis translation cache keys so any cached bad English
translations cannot be served back.

Usage:
    docker compose exec backend python scripts/repair_inverted_zh.py
    docker compose exec backend python scripts/repair_inverted_zh.py --execute
"""

import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from motor.motor_asyncio import AsyncIOMotorClient


_CJK_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))


def _looks_cjk(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    cjk = 0
    total = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in _CJK_RANGES):
            cjk += 1
    if total < 10:
        return False
    return cjk >= 3 and cjk / total >= 0.01


def _looks_ascii(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    non_ascii = 0
    total = 0
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        if ord(ch) > 127:
            non_ascii += 1
    return total >= 10 and non_ascii / total < 0.01


async def _scan_portfolio_orders(db, dry_run: bool) -> int:
    print("\n--- portfolio_orders.metadata.full_research ---")
    coll = db["portfolio_orders"]
    cursor = coll.find(
        {"metadata.full_research_zh": {"$exists": True, "$ne": None}},
        {"_id": 1, "symbol": 1, "metadata.full_research": 1, "metadata.full_research_zh": 1},
    )
    to_fix = []
    async for d in cursor:
        meta = d.get("metadata") or {}
        base = meta.get("full_research") or ""
        zh = meta.get("full_research_zh") or ""
        if _looks_cjk(base) and _looks_ascii(zh):
            to_fix.append((d["_id"], d.get("symbol"), base, zh[:60].replace("\n", " ")))

    print(f"Found inverted rows: {len(to_fix)}")
    for i, (_id, sym, base, zh_head) in enumerate(to_fix[:5]):
        print(f"  [{i+1}] {sym}: zh head='{zh_head}...'")

    if dry_run or not to_fix:
        return len(to_fix)

    fixed = 0
    for _id, _sym, base, _zh in to_fix:
        await coll.update_one({"_id": _id}, {"$set": {"metadata.full_research_zh": base}})
        fixed += 1
    print(f"Repaired: {fixed}")
    return fixed


async def _scan_messages(db, dry_run: bool) -> int:
    print("\n--- messages.content / content_zh ---")
    coll = db["messages"]
    cursor = coll.find(
        {"content_zh": {"$exists": True, "$ne": None}},
        {"_id": 1, "chat_id": 1, "role": 1, "content": 1, "content_zh": 1},
    )
    to_fix = []
    async for d in cursor:
        base = d.get("content") or ""
        zh = d.get("content_zh") or ""
        if _looks_cjk(base) and _looks_ascii(zh):
            to_fix.append((d["_id"], d.get("chat_id"), d.get("role"), base, zh[:60].replace("\n", " ")))

    print(f"Found inverted rows: {len(to_fix)}")
    for i, (_id, cid, role, _base, zh_head) in enumerate(to_fix[:5]):
        print(f"  [{i+1}] chat={cid} role={role}: zh head='{zh_head}...'")

    if dry_run or not to_fix:
        return len(to_fix)

    fixed = 0
    for _id, _cid, _role, base, _zh in to_fix:
        await coll.update_one({"_id": _id}, {"$set": {"content_zh": base}})
        fixed += 1
    print(f"Repaired: {fixed}")
    return fixed


async def _flush_translation_cache(dry_run: bool) -> int:
    print("\n--- Redis: flush translation cache ---")
    try:
        import redis.asyncio as redis  # type: ignore
    except ImportError:
        print("redis package not available — skipping cache flush")
        return 0

    client = redis.Redis(host="redis", port=6379, decode_responses=True)
    try:
        await client.ping()
    except Exception as e:
        print(f"Redis unreachable: {e} — skipping")
        await client.aclose()
        return 0

    # Translator key prefix is `llm_translation:<lang>:<sha1>`; flush zh-CN.
    pattern = "llm_translation:zh-CN:*"
    count = 0
    async for key in client.scan_iter(match=pattern):
        count += 1
        if not dry_run:
            await client.delete(key)
    print(f"Matched keys: {count}  ({'would delete' if dry_run else 'deleted'})")
    await client.aclose()
    return count


async def main() -> None:
    execute = "--execute" in sys.argv
    dry_run = not execute

    print("=" * 72)
    print("REPAIR: inverted *_zh translations")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will modify)'}")
    print("=" * 72)

    if execute:
        confirm = input("\nType 'REPAIR' to proceed: ")
        if confirm != "REPAIR":
            print("Aborted.")
            return

    client = AsyncIOMotorClient("mongodb://mongodb:27017")
    db = client["financial_agent"]

    a = await _scan_portfolio_orders(db, dry_run)
    b = await _scan_messages(db, dry_run)
    c = await _flush_translation_cache(dry_run)

    print("\n" + "=" * 72)
    print(f"portfolio_orders rows{' to fix' if dry_run else ' fixed'}: {a}")
    print(f"messages rows{' to fix' if dry_run else ' fixed'}: {b}")
    print(f"redis keys{' matched' if dry_run else ' deleted'}: {c}")
    print("=" * 72)

    if dry_run and (a or b or c):
        print("\nTo apply, re-run with --execute")


if __name__ == "__main__":
    asyncio.run(main())
