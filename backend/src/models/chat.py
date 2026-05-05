"""
Chat models for conversation management and UI state restoration.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UIState(BaseModel):
    """
    UI state for restoring chat interface.
    Stores only current selections, not data (data lives in messages).
    """

    current_symbol: str | None = Field(
        default=None, description="Currently selected symbol"
    )
    current_company_name: str | None = Field(
        default=None, description="Company name for currently selected symbol"
    )
    current_interval: str = Field(
        default="1d", description="Current timeframe (1h, 1d, 1w, 1mo)"
    )
    current_date_range: dict[str, str | None] = Field(
        default={"start": None, "end": None},
        description="Custom date range if any",
    )
    active_overlays: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Active chart overlays {overlay_name: config_dict}",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "current_symbol": "AAPL",
                "current_interval": "1d",
                "current_date_range": {"start": "2025-01-01", "end": "2025-10-04"},
                "active_overlays": {
                    "fibonacci": {"enabled": True, "levels": [0.236, 0.382, 0.618]},
                    "stochastic": {"enabled": True, "k_period": 14},
                },
            }
        }


class ChatCreate(BaseModel):
    """Request model for creating a new chat."""

    title: str = Field("New Chat", description="Chat title")


class ChatUpdate(BaseModel):
    """Request model for updating chat metadata."""

    title: str | None = None
    is_archived: bool | None = None
    ui_state: UIState | None = None
    last_message_preview: str | None = None


class Chat(BaseModel):
    """
    Chat model for database storage.
    Contains conversation metadata and UI state for restoration.
    """

    chat_id: str = Field(..., description="Unique chat identifier")
    title: str = Field("New Chat", description="Chat title")
    is_archived: bool = Field(False, description="Archive status")

    # UI state for restoration (minimal - messages contain actual data)
    ui_state: UIState = Field(default=UIState(), description="UI restoration state")

    # Denormalized preview for chat list (avoids loading all messages)
    last_message_preview: str | None = Field(
        None, max_length=200, description="Preview of last message"
    )
    title_zh: str | None = Field(
        default=None,
        description="Simplified Chinese translation of title",
    )
    last_message_preview_zh: str | None = Field(
        default=None,
        description="Simplified Chinese translation of last_message_preview",
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_message_at: datetime | None = Field(None, description="Last message timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "chat_id": "chat_abc123",
                "title": "AAPL Analysis",
                "is_archived": False,
                "ui_state": {
                    "current_symbol": "AAPL",
                    "current_interval": "1d",
                    "current_date_range": {"start": None, "end": None},
                    "active_overlays": {"fibonacci": {"enabled": True}},
                },
                "last_message_preview": "Based on the Fibonacci levels, AAPL shows...",
                "created_at": "2025-10-05T10:00:00Z",
                "updated_at": "2025-10-05T10:15:00Z",
                "last_message_at": "2025-10-05T10:15:00Z",
            }
        }


class ChatInDB(Chat):
    """Chat model with database ID."""

    id: str = Field(alias="_id")
