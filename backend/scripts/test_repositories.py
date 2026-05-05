"""
Test script to verify repository layer with local MongoDB.
Run with: python -m scripts.test_repositories
"""

import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient

from src.database.redis import RedisCache
from src.database.repositories import ChatRepository, MessageRepository, UserRepository
from src.models.chat import ChatCreate, ChatUpdate, UIState
from src.models.message import MessageCreate, MessageMetadata
from src.models.user import UserCreate


async def main():
    """Test all repository operations."""

    # Connect to MongoDB (use 'mongodb' hostname when running in Docker)
    client = AsyncIOMotorClient("mongodb://mongodb:27017")
    db = client["financial_agent_test"]

    # Connect to Redis (used by MessageRepository's write-time translator)
    redis_cache = RedisCache()
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    await redis_cache.connect(redis_url)

    # Get collections
    users_collection = db["users"]
    chats_collection = db["chats"]
    messages_collection = db["messages"]

    # Clear test collections
    await users_collection.delete_many({})
    await chats_collection.delete_many({})
    await messages_collection.delete_many({})

    print("🧪 Testing Repository Layer\n")

    # Initialize repositories
    user_repo = UserRepository(users_collection)
    chat_repo = ChatRepository(chats_collection, redis_cache)
    message_repo = MessageRepository(messages_collection, redis_cache)

    # ===== Test UserRepository =====
    print("📝 Testing UserRepository...")

    # Create user
    user_create = UserCreate(phone_number="+1234567890", username="TestUser")
    user = await user_repo.create(user_create)
    print(f"✅ Created user: {user.user_id} | {user.username}")

    # Get by ID
    fetched_user = await user_repo.get_by_id(user.user_id)
    assert fetched_user is not None
    print(f"✅ Fetched user by ID: {fetched_user.user_id}")

    # Get by phone
    fetched_user = await user_repo.get_by_phone("+1234567890")
    assert fetched_user is not None
    print(f"✅ Fetched user by phone: {fetched_user.phone_number}")

    # Update last login
    updated_user = await user_repo.update_last_login(user.user_id)
    assert updated_user.last_login is not None
    print(f"✅ Updated last_login: {updated_user.last_login}")

    print()

    # ===== Test ChatRepository =====
    print("💬 Testing ChatRepository...")

    # Create chat
    chat_create = ChatCreate(title="AAPL Analysis", user_id=user.user_id)
    chat = await chat_repo.create(chat_create)
    print(f"✅ Created chat: {chat.chat_id} | {chat.title}")

    # Get chat
    fetched_chat = await chat_repo.get(chat.chat_id)
    assert fetched_chat is not None
    print(f"✅ Fetched chat: {fetched_chat.chat_id}")

    # List user's chats
    chats = await chat_repo.list_by_user(user.user_id)
    assert len(chats) == 1
    print(f"✅ Listed user chats: {len(chats)} chat(s)")

    # Update UI state
    ui_state = UIState(
        current_symbol="AAPL",
        current_interval="1d",
        current_date_range={"start": "2025-01-01", "end": "2025-10-04"},
    )
    updated_chat = await chat_repo.update_ui_state(chat.chat_id, ui_state)
    assert updated_chat.ui_state.current_symbol == "AAPL"
    print(f"✅ Updated UI state: symbol={updated_chat.ui_state.current_symbol}")

    # Update chat metadata
    chat_update = ChatUpdate(title="AAPL Technical Analysis", is_archived=False)
    updated_chat = await chat_repo.update(chat.chat_id, chat_update)
    assert updated_chat.title == "AAPL Technical Analysis"
    print(f"✅ Updated chat title: {updated_chat.title}")

    print()

    # ===== Test MessageRepository =====
    print("📨 Testing MessageRepository...")

    # Create user message
    user_msg = MessageCreate(
        chat_id=chat.chat_id,
        role="user",
        content="Analyze AAPL fibonacci levels",
        source="user",
    )
    created_msg = await message_repo.create(user_msg)
    print(f"✅ Created user message: {created_msg.message_id}")

    # Update last_message_at in chat
    await chat_repo.update_last_message_at(chat.chat_id)

    # Create Fibonacci analysis message
    fib_metadata = MessageMetadata(
        symbol="AAPL",
        timeframe="1d",
        fibonacci_levels=[
            {"level": 0, "price": 150.0, "percentage": "0%"},
            {"level": 0.618, "price": 186.18, "percentage": "61.8%"},
        ],
        trend_direction="uptrend",
        swing_high={"price": 210.0, "date": "2025-10-01"},
        swing_low={"price": 150.0, "date": "2025-09-01"},
        confidence_score=0.85,
    )

    fib_msg = MessageCreate(
        chat_id=chat.chat_id,
        role="assistant",
        content="## Fibonacci Analysis - AAPL\n\nLevels calculated...",
        source="fibonacci",
        metadata=fib_metadata,
    )
    created_fib = await message_repo.create(fib_msg)
    print(f"✅ Created Fibonacci message: {created_fib.message_id}")

    # Get messages by chat
    messages = await message_repo.get_by_chat(chat.chat_id)
    assert len(messages) == 2
    print(f"✅ Fetched messages: {len(messages)} message(s)")

    # Get Fibonacci messages
    fib_messages = await message_repo.get_fibonacci_messages(
        chat.chat_id, symbol="AAPL"
    )
    assert len(fib_messages) == 1
    assert fib_messages[0].metadata.symbol == "AAPL"
    print(f"✅ Fetched Fibonacci messages: {len(fib_messages)} message(s)")

    # Get messages in reverse
    reverse_messages = await message_repo.get_by_chat_reverse(chat.chat_id, limit=10)
    assert len(reverse_messages) == 2
    assert reverse_messages[0].message_id == created_fib.message_id  # Newest first
    print(f"✅ Fetched reverse messages: newest is {reverse_messages[0].source}")

    # Count messages
    count = await message_repo.count_by_chat(chat.chat_id)
    assert count == 2
    print(f"✅ Counted messages: {count} message(s)")

    print()

    # ===== Test Cascade Delete =====
    print("🗑️  Testing cascade delete...")

    # Delete messages
    deleted_count = await message_repo.delete_by_chat(chat.chat_id)
    assert deleted_count == 2
    print(f"✅ Deleted messages: {deleted_count} message(s)")

    # Delete chat
    deleted = await chat_repo.delete(chat.chat_id)
    assert deleted is True
    print(f"✅ Deleted chat: {chat.chat_id}")

    print()
    print("✨ All repository tests passed!")

    # Close connection
    await redis_cache.disconnect()
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
