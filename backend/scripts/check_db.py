#!/usr/bin/env python3
"""Quick check of MongoDB contents for deep analysis messages."""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient


async def check():
    client = AsyncIOMotorClient("mongodb://mongodb:27017/financial_agent")
    db = client.get_default_database()

    colls = await db.list_collection_names()
    print("Collections:", colls)

    if "messages" not in colls:
        print("No messages collection!")
        client.close()
        return

    count = await db["messages"].count_documents({})
    print(f"Messages total: {count}")

    # Check metadata.agent_type values
    pipeline = [
        {"$match": {"metadata": {"$exists": True}}},
        {"$group": {"_id": "$metadata.agent_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    print("\nAgent types in metadata:")
    async for doc in db["messages"].aggregate(pipeline):
        print(f"  {doc['_id']}: {doc['count']}")

    # Check source field distribution
    pipeline2 = [
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    print("\nSource distribution:")
    async for doc in db["messages"].aggregate(pipeline2):
        print(f"  {doc['_id']}: {doc['count']}")

    # Look for any message with raw_data or deep_events
    deep_events = await db["messages"].count_documents(
        {"metadata.raw_data.deep_events": {"$exists": True}}
    )
    print(f"\nMessages with deep_events: {deep_events}")

    # Sample a few recent messages with metadata
    print("\nLatest 5 messages with metadata:")
    cursor = db["messages"].find(
        {"metadata": {"$exists": True, "$ne": None}},
        sort=[("timestamp", -1)],
        limit=5,
    )
    async for doc in cursor:
        meta = doc.get("metadata", {})
        meta_keys = list(meta.keys()) if isinstance(meta, dict) else str(type(meta))
        content_preview = str(doc.get("content", ""))[:80]
        print(
            f"  role={doc.get('role')} | source={doc.get('source')} | "
            f"agent_type={meta.get('agent_type', 'N/A')} | "
            f"meta_keys={meta_keys}"
        )
        print(f"    content: {content_preview}")

    client.close()


if __name__ == "__main__":
    asyncio.run(check())
