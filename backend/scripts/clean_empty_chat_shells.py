#!/usr/bin/env python3
"""
Clean up empty chat shells left behind by the frontend symbol-select handler.

`EnhancedChatInterface.handleSymbolSelect` auto-creates a fresh chat on every
symbol selection. Many of those never receive a message and stick around as
empty shells with `last_message_at=None` and zero rows in the `messages`
collection. Once they age past a day, they are abandoned for sure; left
unchecked, they dominate page 1 of the chat list.

This script deletes those abandoned shells:
  * `last_message_at IS NULL`
  * `chat_id` does NOT appear in the `messages` collection
  * `created_at < now - 1 day`

Default mode is `--dry-run` (prints what it would delete). Pass `--execute`
and confirm by typing `DELETE` at the prompt to actually delete.

Idempotent — re-running after `--execute` finds zero candidates.
"""

import asyncio
import sys
from datetime import timedelta
from pathlib import Path

# Add backend src to path so we can import shared utilities consistently with
# sibling scripts (see backend/scripts/cleanup_user_portfolio_chats.py).
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir / "src"))


from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from core.utils.date_utils import utcnow  # noqa: E402

_ABANDON_AFTER = timedelta(days=1)


async def clean_empty_chat_shells(dry_run: bool = True) -> None:
    """Find and (optionally) delete abandoned empty chat shells.

    Args:
        dry_run: If True, only print what would be deleted. Default True.
    """
    client = AsyncIOMotorClient("mongodb://mongodb:27017")
    db = client["financial_agent"]
    chats_collection = db["chats"]
    messages_collection = db["messages"]

    print("=" * 80)
    print("CLEANUP: Empty Chat Shells")
    print("=" * 80)
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will delete)'}")
    print("=" * 80)
    print()

    cutoff = utcnow() - _ABANDON_AFTER

    total_before = await chats_collection.count_documents({})
    print(f"Total chats in DB: {total_before}")

    # Set of chat_ids that have at least one message — these are NEVER candidates.
    messages_chat_ids = set(await messages_collection.distinct("chat_id"))
    print(f"Chats with messages: {len(messages_chat_ids)}")

    # Candidate filter: never-messaged, older than the abandonment cutoff.
    candidate_cursor = chats_collection.find(
        {
            "last_message_at": None,
            "created_at": {"$lt": cutoff},
        }
    )
    candidates = await candidate_cursor.to_list(length=None)
    print(f"Pre-filter candidates (no last_message_at, >1d old): {len(candidates)}")

    # Second-pass filter in Python: drop any chat that still has rows in
    # `messages` (defensive — last_message_at can lag behind a real message).
    to_delete = [c for c in candidates if c.get("chat_id") not in messages_chat_ids]
    print(f"Confirmed empty shells to delete: {len(to_delete)}")
    print()

    if not to_delete:
        print("Nothing to clean up - database is already tidy.")
        return

    sample = to_delete[:5]
    print(f"Sample of {len(sample)} shells:")
    for idx, doc in enumerate(sample, 1):
        print(f"  {idx}. chat_id={doc.get('chat_id')}")
        print(f"     title={doc.get('title', 'Untitled')!r}")
        print(f"     created_at={doc.get('created_at')}")
    print()

    if dry_run:
        print("=" * 80)
        print("DRY RUN - No changes made")
        print("=" * 80)
        print("\nTo actually delete these shells, run:")
        print(
            "  docker compose exec backend python scripts/clean_empty_chat_shells.py --execute"
        )
        return

    print("=" * 80)
    print("EXECUTING DELETION")
    print("=" * 80)
    print()

    ids_to_delete = [doc["chat_id"] for doc in to_delete]
    result = await chats_collection.delete_many(
        {"chat_id": {"$in": ids_to_delete}}
    )

    total_after = await chats_collection.count_documents({})
    print(f"Deleted: {result.deleted_count} chats")
    print(f"Total chats before: {total_before}")
    print(f"Total chats after:  {total_after}")


async def main() -> None:
    execute = "--execute" in sys.argv

    if execute:
        print("\nWARNING: This will DELETE empty chat shells from the database.")
        print("Make sure you have a backup if needed.\n")
        response = input("Type 'DELETE' to confirm: ")
        if response != "DELETE":
            print("Aborted.")
            return
        print()

    await clean_empty_chat_shells(dry_run=not execute)


if __name__ == "__main__":
    asyncio.run(main())
