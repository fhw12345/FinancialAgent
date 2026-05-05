"""Backfill historical MongoDB documents with zh-CN translations.

Scans collections for documents missing `<field>_zh` and populates them
in batches by calling persistence_translator. Idempotent: documents that
already have translations are skipped.

Usage:
    docker compose exec backend python -m scripts.backfill_translations \\
        [--collection messages|chats|all] \\
        [--batch-size 50] \\
        [--limit N] \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorCollection

from src.services.persistence_translator import translate_for_persistence

if TYPE_CHECKING:
    from src.database.redis import RedisCache

logger = logging.getLogger("backfill_translations")


COLLECTION_FIELDS: dict[str, list[str]] = {
    "messages": ["content"],
    "chats": ["title", "last_message_preview"],
}


def _missing_query(text_fields: list[str]) -> dict:
    """Match documents where any text field is non-empty but its _zh sibling is missing."""
    return {
        "$or": [
            {
                "$and": [
                    {field: {"$exists": True, "$nin": [None, ""]}},
                    {
                        "$or": [
                            {f"{field}_zh": {"$exists": False}},
                            {f"{field}_zh": None},
                        ]
                    },
                ]
            }
            for field in text_fields
        ]
    }


async def backfill_collection(
    collection: AsyncIOMotorCollection,
    text_fields: list[str],
    redis_cache: RedisCache,
    batch_size: int = 50,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Backfill `_zh` fields on a single collection. Returns stats."""
    stats = {"scanned": 0, "updated": 0, "would_update": 0, "failed": 0}

    query = _missing_query(text_fields)
    cursor = collection.find(query)
    if limit:
        cursor = cursor.limit(limit)

    batch: list[dict] = []
    async for doc in cursor:
        stats["scanned"] += 1
        batch.append(doc)
        if len(batch) >= batch_size:
            await _process_batch(
                collection, batch, text_fields, redis_cache, dry_run, stats
            )
            batch = []
    if batch:
        await _process_batch(
            collection, batch, text_fields, redis_cache, dry_run, stats
        )

    logger.info("backfill complete: %s", stats)
    return stats


async def _process_batch(
    collection: AsyncIOMotorCollection,
    batch: list[dict],
    text_fields: list[str],
    redis_cache: RedisCache,
    dry_run: bool,
    stats: dict[str, int],
) -> None:
    for doc in batch:
        to_translate = {
            f: doc[f] for f in text_fields if doc.get(f) and doc.get(f"{f}_zh") is None
        }
        if not to_translate:
            continue

        translations = await translate_for_persistence(
            to_translate, redis_cache=redis_cache
        )

        any_failed = any(v is None for v in translations.values())
        if any_failed:
            stats["failed"] += 1

        any_succeeded = any(v is not None for v in translations.values())
        if not any_succeeded:
            continue

        if dry_run:
            stats["would_update"] += 1
            continue

        update_doc = {k: v for k, v in translations.items() if v is not None}
        result = await collection.update_one({"_id": doc["_id"]}, {"$set": update_doc})
        if result.modified_count == 1:
            stats["updated"] += 1


async def _main(args: argparse.Namespace) -> None:
    # Adapted for this codebase: there is no top-level `get_database` /
    # `get_redis_cache` accessor. We mirror the connection dance used by
    # `backend/scripts/test_repositories.py` and `backend/src/main.py:lifespan`,
    # driving connections from `Settings` (mongodb_url / redis_url).
    from src.core.config import get_settings
    from src.database.mongodb import MongoDB
    from src.database.redis import RedisCache

    settings = get_settings()

    mongodb = MongoDB()
    redis_cache = RedisCache()

    try:
        await mongodb.connect(settings.mongodb_url)
        await redis_cache.connect(settings.redis_url)

        if mongodb.database is None:
            raise RuntimeError("MongoDB.connect returned without populating database")
        db = mongodb.database

        targets = (
            list(COLLECTION_FIELDS.keys())
            if args.collection == "all"
            else [args.collection]
        )

        for coll_name in targets:
            coll = db[coll_name]
            fields = COLLECTION_FIELDS[coll_name]
            logger.info(
                "backfilling collection=%s fields=%s batch_size=%d dry_run=%s",
                coll_name,
                fields,
                args.batch_size,
                args.dry_run,
            )
            await backfill_collection(
                coll,
                text_fields=fields,
                redis_cache=redis_cache,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=args.dry_run,
            )
    finally:
        await redis_cache.disconnect()
        await mongodb.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        choices=["messages", "chats", "all"],
        default="all",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
