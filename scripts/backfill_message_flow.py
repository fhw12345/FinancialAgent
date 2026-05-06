"""
One-shot backfill: stamp metadata.raw_data.flow on historical decision messages.

History card titles (chats.py) decide between 持仓分析 / 今日推荐 / Analysis
based on metadata.raw_data.flow. This field was added with the Mark-Executed
feature; messages written before that release have raw_data without `flow`,
so they fall back to the generic "Analysis" prefix.

Discrimination rules:
  1. portfolio_run_summary messages — chat_id encodes the flow:
       system-run-holdings-YYYY-MM-DD → flow=holdings
       system-run-picks-YYYY-MM-DD    → flow=picks
  2. portfolio messages (chat="Portfolio Decisions") — find portfolio_orders
     created within ±30min whose symbol is in the message's symbols_analyzed
     list. The order_id prefix (holdings_/picks_) is authoritative. Skip the
     write if the matched orders disagree (mixed-flow runs are rare and we
     don't want to guess).

Run inside the backend container so MongoDB DNS resolves to the docker
service name:
  docker compose exec -T backend python /app/scripts/backfill_message_flow.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

# /app/scripts/<this>.py — make `src` importable when run as
# `python scripts/backfill_message_flow.py` from /app inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings  # noqa: E402
from src.database.mongodb import MongoDB  # noqa: E402


async def main(dry_run: bool) -> int:
    settings = get_settings()
    mongodb = MongoDB()
    await mongodb.connect(settings.mongodb_url)
    db = mongodb.database
    if db is None:
        print("ERROR: failed to obtain database handle")
        return 1
    messages = db["messages"]
    orders = db["portfolio_orders"]

    summary_writes = 0
    summary_skips = 0
    portfolio_writes = 0
    portfolio_skips = 0
    portfolio_ambiguous = 0

    # ---- 1. portfolio_run_summary: derive flow from chat_id ----
    cursor = messages.find({"metadata.analysis_type": "portfolio_run_summary"})
    async for msg in cursor:
        chat_id = msg.get("chat_id") or ""
        existing_flow = (msg.get("metadata") or {}).get("raw_data") or {}
        if isinstance(existing_flow, dict) and existing_flow.get("flow"):
            summary_skips += 1
            continue

        if "-holdings-" in chat_id:
            flow = "holdings"
        elif "-picks-" in chat_id:
            flow = "picks"
        else:
            print(f"[summary] SKIP unrecognized chat_id: {chat_id}")
            summary_skips += 1
            continue

        if dry_run:
            print(f"[summary] WOULD set flow={flow} on msg {msg.get('message_id')}"
                  f" (chat={chat_id})")
        else:
            existing_rd = (msg.get("metadata") or {}).get("raw_data") or {}
            if not isinstance(existing_rd, dict):
                existing_rd = {}
            existing_rd["flow"] = flow
            await messages.update_one(
                {"_id": msg["_id"]},
                {"$set": {"metadata.raw_data": existing_rd}},
            )
        summary_writes += 1

    # ---- 2. portfolio: derive flow from related portfolio_orders ----
    cursor = messages.find({"metadata.analysis_type": "portfolio"})
    async for msg in cursor:
        meta = msg.get("metadata") or {}
        raw_data = meta.get("raw_data") or {}
        if raw_data.get("flow"):
            portfolio_skips += 1
            continue

        ts = msg.get("timestamp")
        syms = raw_data.get("symbols_analyzed") or []
        if not ts or not syms:
            print(f"[portfolio] SKIP no timestamp/symbols on msg "
                  f"{msg.get('message_id')}")
            portfolio_skips += 1
            continue

        lo = ts - timedelta(minutes=30)
        hi = ts + timedelta(minutes=5)
        matched = await orders.find(
            {
                "created_at": {"$gte": lo, "$lte": hi},
                "symbol": {"$in": syms},
            }
        ).to_list(length=None)

        prefixes = {
            (o.get("order_id") or "").split("_")[0]
            for o in matched
            if "_" in (o.get("order_id") or "")
        }
        prefixes.discard("")

        if not prefixes:
            print(f"[portfolio] SKIP no matched orders for msg "
                  f"{msg.get('message_id')} ts={ts.isoformat()} syms={syms[:3]}")
            portfolio_skips += 1
            continue

        if len(prefixes) > 1:
            # Mixed-flow window: filter orders to those whose symbol is in
            # this message's symbols_analyzed AND created closest to ts.
            # If symbols give a unique prefix that wins; otherwise skip.
            tight_matched = [
                o for o in matched
                if abs((o.get("created_at") - ts).total_seconds()) <= 120
            ]
            tight_prefixes = {
                (o.get("order_id") or "").split("_")[0]
                for o in tight_matched
                if "_" in (o.get("order_id") or "")
            }
            tight_prefixes.discard("")
            if len(tight_prefixes) == 1:
                prefixes = tight_prefixes
            else:
                print(f"[portfolio] AMBIGUOUS msg {msg.get('message_id')} "
                      f"ts={ts.isoformat()} prefixes={prefixes} "
                      f"tight={tight_prefixes} — leaving blank")
                portfolio_ambiguous += 1
                continue

        flow = next(iter(prefixes))
        if flow not in ("holdings", "picks"):
            print(f"[portfolio] SKIP unknown prefix {flow!r} on msg "
                  f"{msg.get('message_id')}")
            portfolio_skips += 1
            continue

        if dry_run:
            print(f"[portfolio] WOULD set flow={flow} on msg "
                  f"{msg.get('message_id')} ts={ts.isoformat()} syms={syms[:3]}")
        else:
            existing_rd = raw_data if isinstance(raw_data, dict) else {}
            existing_rd["flow"] = flow
            await messages.update_one(
                {"_id": msg["_id"]},
                {"$set": {"metadata.raw_data": existing_rd}},
            )
        portfolio_writes += 1

    print()
    print(f"portfolio_run_summary  written={summary_writes}  skipped={summary_skips}")
    print(f"portfolio              written={portfolio_writes}  skipped={portfolio_skips}  ambiguous={portfolio_ambiguous}")
    if dry_run:
        print("DRY RUN — no writes performed.")
    await mongodb.disconnect()
    return 0


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    sys.exit(asyncio.run(main(dry)))
