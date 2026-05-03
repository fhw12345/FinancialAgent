#!/usr/bin/env python3
"""
Admin script to top up user credits.

Usage:
    python scripts/topup_credits.py <username> <amount>
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from motor.motor_asyncio import AsyncIOMotorClient

from core.config import get_settings


async def topup_credits(username: str, target_amount: float):
    """Top up user credits to target amount."""
    settings = get_settings()

    # Connect to MongoDB
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.database_name]
    users_collection = db["users"]

    try:
        # Find user by username
        user = await users_collection.find_one({"username": username})

        if not user:
            print(f"❌ Error: User '{username}' not found")
            return False

        current_credits = user.get("credits", 0.0)
        user_id = user.get("user_id")

        print("\n📊 Current Status:")
        print(f"   User: {username}")
        print(f"   User ID: {user_id}")
        print(f"   Current Credits: {current_credits}")
        print(f"   Target Amount: {target_amount}")

        # Update credits
        result = await users_collection.update_one(
            {"user_id": user_id}, {"$set": {"credits": target_amount}}
        )

        if result.modified_count > 0:
            print(f"\n✅ Success! Credits updated to {target_amount}")

            # Verify the update
            updated_user = await users_collection.find_one({"user_id": user_id})
            print(f"   Verified Credits: {updated_user.get('credits', 0.0)}")
            return True
        else:
            print(f"\n⚠️  No changes made (credits already at {target_amount})")
            return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False
    finally:
        client.close()


async def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python scripts/topup_credits.py <username> <amount>")
        print("Example: python scripts/topup_credits.py myuser 1000")
        sys.exit(1)

    username = sys.argv[1]
    try:
        amount = float(sys.argv[2])
    except ValueError:
        print(f"❌ Error: Invalid amount '{sys.argv[2]}'. Must be a number.")
        sys.exit(1)

    if amount < 0:
        print("❌ Error: Amount must be positive")
        sys.exit(1)

    print(f"🚀 Topping up credits for user: {username}")
    print(f"   Target amount: {amount}")

    success = await topup_credits(username, amount)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
