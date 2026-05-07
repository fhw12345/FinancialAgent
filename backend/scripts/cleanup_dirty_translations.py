#!/usr/bin/env python3
"""Cleanup dirty translation fields where ``<field>_zh`` accidentally equals
its English source.

A historical bug stored the original English text into the ``*_zh`` field,
producing rows where the "translation" is byte-identical to the source. The
frontend cannot tell these apart from real translations, so they pollute the
zh display. This script finds those rows and sets the ``*_zh`` field to
``None`` (not ``$unset`` — we preserve the field so the frontend type stays
consistent and can fall back gracefully).

Default mode is dry-run. Pass ``--apply`` to actually clear the fields.

Run inside the backend container::

    docker compose exec backend python scripts/cleanup_dirty_translations.py
    docker compose exec backend python scripts/cleanup_dirty_translations.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Make ``backend/`` importable so ``src.*`` resolves the same way as in main.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import get_settings  # noqa: E402
from src.database.mongodb import MongoDB  # noqa: E402

# (collection_name, en_field_path, zh_field_path) — paths may be dotted.
CHECKS: list[tuple[str, str, str]] = [
    ("messages", "content", "content_zh"),
    ("chats", "title", "title_zh"),
    ("chats", "last_message_preview", "last_message_preview_zh"),
    ("portfolio_orders", "metadata.reasoning", "metadata.reasoning_zh"),
    ("portfolio_orders", "metadata.full_research", "metadata.full_research_zh"),
]


def build_dirty_query(en_path: str, zh_path: str) -> dict[str, Any]:
    """Build a Mongo filter matching docs where ``zh_path == en_path`` and
    the zh value is non-null / non-empty. Uses ``$expr`` so dotted paths work
    against arbitrary nested fields.
    """
    return {
        "$expr": {
            "$and": [
                {"$ne": [f"${zh_path}", None]},
                {"$ne": [f"${zh_path}", ""]},
                {"$eq": [f"${zh_path}", f"${en_path}"]},
            ]
        }
    }


def _get_nested(doc: dict[str, Any], path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


async def scan_dirty(coll: Any, en_path: str, zh_path: str) -> list[dict[str, Any]]:
    """Return a list of ``{_id, en_len, zh_len}`` records for dirty docs."""
    query = build_dirty_query(en_path, zh_path)
    cursor = coll.find(query)
    out: list[dict[str, Any]] = []
    async for d in cursor:
        en = _get_nested(d, en_path)
        zh = _get_nested(d, zh_path)
        out.append(
            {
                "_id": d.get("_id"),
                "en_len": len(en) if isinstance(en, str) else 0,
                "zh_len": len(zh) if isinstance(zh, str) else 0,
            }
        )
    return out


async def cleanup_one(
    coll: Any, en_path: str, zh_path: str, dry_run: bool
) -> int:
    dirty = await scan_dirty(coll, en_path, zh_path)
    name = getattr(coll, "name", "<coll>")
    print(f"  {name}.{zh_path}: {len(dirty)} dirty doc(s)")
    if not dirty:
        return 0
    if dry_run:
        print(f"    would clear {len(dirty)} doc(s) (dry-run)")
        return len(dirty)
    ids = [d["_id"] for d in dirty]
    result = await coll.update_many(
        {"_id": {"$in": ids}},
        {"$set": {zh_path: None}},
    )
    matched = getattr(result, "matched_count", "?")
    modified = getattr(result, "modified_count", "?")
    print(f"    cleared: matched={matched} modified={modified}")
    return len(dirty)


async def _main(dry_run: bool) -> None:
    settings = get_settings()
    mongodb = MongoDB()
    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"=== cleanup_dirty_translations  mode={mode} ===")
    try:
        await mongodb.connect(settings.mongodb_url)
        if mongodb.database is None:
            raise RuntimeError("MongoDB.connect did not populate database")
        db = mongodb.database
        total = 0
        for coll_name, en_path, zh_path in CHECKS:
            coll = db[coll_name]
            total += await cleanup_one(coll, en_path, zh_path, dry_run)
        print(f"=== total dirty docs: {total} ===")
    finally:
        await mongodb.disconnect()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually clear the dirty *_zh fields. Default is dry-run.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(_main(dry_run=not args.apply))
