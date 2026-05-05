"""
Analysis history endpoint.

Provides access to historical analysis data and message timelines
for portfolio tracking and analysis review.
"""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request

logger = structlog.get_logger()
router = APIRouter()


@router.get("/history")
async def get_analysis_history(
    request: Request,
    symbol: str | None = None,
    analysis_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Get analysis history messages.

    Query parameters:
    - symbol: Filter by stock symbol (e.g., AAPL)
    - analysis_id: Filter by specific analysis workflow ID
    - limit: Maximum number of messages to return (default: 100)

    Returns analysis messages from the message collection grouped by analysis_id.
    Used for portfolio chart markers and analysis timeline.
    """
    try:
        from ...database.repositories.message_repository import MessageRepository

        # Get MongoDB connection from app state
        mongodb = request.app.state.mongodb
        redis_cache = request.app.state.redis
        messages_collection = mongodb.get_collection("messages")
        message_repo = MessageRepository(messages_collection, redis_cache)

        # Query analysis messages
        messages = await message_repo.get_analysis_messages(
            symbol=symbol,
            analysis_id=analysis_id,
            limit=limit,
        )

        # Group by analysis_id
        analysis_sessions: dict[str, list] = {}
        for msg in messages:
            aid = msg.metadata.analysis_id or "unknown"
            if aid not in analysis_sessions:
                analysis_sessions[aid] = []

            analysis_sessions[aid].append(
                {
                    "message_id": msg.message_id,
                    "timestamp": msg.timestamp.isoformat(),
                    "symbol": msg.metadata.symbol,
                    "content": msg.content[:200],  # Truncate for summary
                    "selected_tool": msg.metadata.selected_tool,
                    "confidence_score": msg.metadata.confidence_score,
                    "trend_direction": msg.metadata.trend_direction,
                }
            )

        logger.info(
            "Analysis history queried",
            symbol=symbol,
            analysis_id=analysis_id,
            message_count=len(messages),
            session_count=len(analysis_sessions),
        )

        return {
            "symbol": symbol,
            "analysis_id": analysis_id,
            "total_messages": len(messages),
            "analysis_sessions": analysis_sessions,
        }

    except Exception as e:
        logger.error(
            "Failed to get analysis history",
            symbol=symbol,
            analysis_id=analysis_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get analysis history: {str(e)}"
        ) from e
