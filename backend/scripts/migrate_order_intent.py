"""Backfill `intent` field on existing portfolio_orders docs (W1.2).

Why this is needed:
  W1.1 added an OrderIntent field + geometry validator to TradingDecision
  (the LLM-output schema). Existing PortfolioOrder docs in mongo predate
  the field and use `side` (buy/sell/hold) + limit_price + stop_price.
  The frontend OrderPreview (W1.3) reads `intent` from metadata to render
  the correct badge; without backfill, historical decisions render as
  "unknown intent".

Inference rules (intentionally conservative):
  side=hold                        -> intent=hold
  side=buy                         -> intent=open_long
  side=sell                        -> intent=close_long  (the common case
                                       in this single-user portfolio flow;
                                       no real short trades have shipped)

Geometry sanity flag (does NOT change intent, only annotates):
  side=sell with stop_price > limit_price (the CRWV-style historical
  bug) gets metadata.legacy_short_geometry = True so a future review can
  surface those docs without breaking schema.

Usage:
    docker compose exec backend python scripts/migrate_order_intent.py
    docker compose exec backend python scripts/migrate_order_intent.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import get_settings  # noqa: E402
from src.database.mongodb import MongoDB  # noqa: E402

INTENT_BY_SIDE = {
    "hold": "hold",
    "buy": "open_long",
    "sell": "close_long",
}


async def main(apply: bool) -> int:
    settings = get_settings()
    mongo = MongoDB()
    await mongo.connect(settings.mongodb_url)
    coll = mongo.get_collection("portfolio_orders")

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== migrate_order_intent  mode={mode} ===")

    total = 0
    by_intent: dict[str, int] = {}
    legacy_geom = 0
    unknown_side = 0
    bulk: list = []

    cursor = coll.find({})
    async for d in cursor:
        total += 1
        side = (d.get("side") or "").lower()
        intent = INTENT_BY_SIDE.get(side)
        if intent is None:
            unknown_side += 1
            continue
        by_intent[intent] = by_intent.get(intent, 0) + 1

        update_set: dict = {"intent": intent}

        # Geometry sanity flag for the CRWV-style historical layout.
        if side == "sell":
            limit = d.get("limit_price")
            stop = d.get("stop_price")
            if (
                isinstance(limit, (int, float))
                and isinstance(stop, (int, float))
                and stop > limit
            ):
                legacy_geom += 1
                update_set["metadata.legacy_short_geometry"] = True

        bulk.append((d["_id"], update_set))

    print(f"  total docs scanned        : {total}")
    for intent, count in sorted(by_intent.items()):
        print(f"  {intent:14s} -> {count}")
    print(f"  legacy_short_geometry flag: {legacy_geom}")
    print(f"  unknown_side (skipped)    : {unknown_side}")

    if not apply:
        print(f"\n  would update: {len(bulk)} docs (re-run with --apply to write)")
        await mongo.disconnect()
        return 0 if unknown_side == 0 else 1

    if not bulk:
        print("  nothing to write")
        await mongo.disconnect()
        return 0

    modified = 0
    for _id, update_set in bulk:
        result = await coll.update_one({"_id": _id}, {"$set": update_set})
        modified += result.modified_count
    print(f"\n  modified: {modified}/{len(bulk)}")
    await mongo.disconnect()
    return 0 if unknown_side == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write intent + legacy flag. Default is dry-run.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(apply=args.apply)))
