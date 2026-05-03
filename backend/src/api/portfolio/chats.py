"""
Portfolio chat endpoints.

Provides:
- GET /chat-history: Portfolio agent chat history grouped by symbol
- GET /chats/{chat_id}: Get specific chat detail
- DELETE /chats/{chat_id}: Delete portfolio chat (admin only)
"""

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from ...database.mongodb import MongoDB
from ...services.chat_service import ChatService
from ..dependencies.auth import get_mongodb, require_admin
from ..dependencies.chat_deps import get_chat_service
from ..dependencies.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter()


@router.get("/chat-history")
@limiter.limit("60/minute")  # Standard read operation
async def get_portfolio_chat_history(
    request: Request,
    symbol: str | None = None,  # Optional symbol filter (e.g., "AAPL")
    start_date: str | None = None,  # Optional start date (YYYY-MM-DD)
    end_date: str | None = None,  # Optional end date (YYYY-MM-DD)
    date: str | None = None,  # Legacy: single date filter (YYYY-MM-DD) - deprecated
    analysis_type: (
        str | None
    ) = None,  # Optional: "individual" (symbol research), "portfolio" (decisions), or None for all
    mongodb: MongoDB = Depends(get_mongodb),
) -> dict:
    """
    Get portfolio agent's chat history grouped by symbol.

    Each symbol has its own chat (e.g., "XIACY Analysis") where all
    analyses for that symbol are stored as messages.
    """
    # W5b: Portfolio chats identified by title pattern (no user_id field).
    try:
        chats_collection = mongodb.get_collection("chats")
        messages_collection = mongodb.get_collection("messages")

        # Parse date filters
        date_start = None
        date_end = None

        # Handle legacy single date filter (convert to date range)
        if date and not start_date and not end_date:
            start_date = date
            # Single date = same day range
            try:
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                date_end = date_obj.replace(hour=23, minute=59, second=59)
            except ValueError as e:
                logger.warning("Invalid date format provided", date=date)
                raise HTTPException(
                    status_code=400, detail="Invalid date format. Use YYYY-MM-DD."
                ) from e

        # Parse start_date
        if start_date:
            try:
                date_start = datetime.strptime(start_date, "%Y-%m-%d").replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            except ValueError as e:
                logger.warning("Invalid start_date format", start_date=start_date)
                raise HTTPException(
                    status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD."
                ) from e

        # Parse end_date
        if end_date:
            try:
                date_end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            except ValueError as e:
                logger.warning("Invalid end_date format", end_date=end_date)
                raise HTTPException(
                    status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD."
                ) from e

        # Get all portfolio-agent style chats (identified by title pattern)
        chat_query: dict = {
            "$or": [
                {"title": {"$regex": r"\sAnalysis$", "$options": "i"}},
                {"title": "Portfolio Decisions"},
            ]
        }

        # Apply symbol filter if provided (filter by title pattern)
        # Note: We always include "Portfolio Decisions" chat and filter by message metadata
        if symbol:
            # Match chats where title starts with symbol (e.g., "AAPL Analysis")
            # OR the "Portfolio Decisions" chat (filtered at message level)
            chat_query = {
                "$or": [
                    {"title": {"$regex": f"^{symbol}\\s", "$options": "i"}},
                    {"title": "Portfolio Decisions"},
                ]
            }

        portfolio_chats = await chats_collection.find(chat_query).to_list(length=None)

        if not portfolio_chats:
            logger.info(
                "No portfolio agent chats found",
                symbol_filter=symbol,
                date_filter=start_date or end_date,
            )
            return {"chats": []}

        logger.info(
            "Found portfolio agent chats",
            count=len(portfolio_chats),
            symbol_filter=symbol,
            start_date=start_date,
            end_date=end_date,
        )

        # Build result: one entry per chat (symbol)
        result_chats = []

        for chat in portfolio_chats:
            chat_id = chat["chat_id"]
            title = chat.get("title", "Unknown")
            is_portfolio_decisions_chat = title == "Portfolio Decisions"

            # Extract symbol from title (format: "{symbol} Analysis")
            # For "Portfolio Decisions" chat, symbol is None (aggregated across symbols)
            chat_symbol = (
                None
                if is_portfolio_decisions_chat
                else (title.split(" ")[0] if " " in title else title)
            )

            # Build message query
            message_query: dict = {"chat_id": chat_id}
            if date_start and date_end:
                # Filter messages by date range
                message_query["timestamp"] = {"$gte": date_start, "$lt": date_end}
            elif date_start:
                # Filter messages from start date onwards
                message_query["timestamp"] = {"$gte": date_start}
            elif date_end:
                # Filter messages up to end date
                message_query["timestamp"] = {"$lt": date_end}

            # Filter by analysis_type if specified
            # For backward compatibility: "individual" also matches messages with null/missing analysis_type
            # (all messages created before this feature are individual symbol analyses)
            if analysis_type:
                if analysis_type == "individual":
                    # Match "individual" OR null/missing (backward compatibility)
                    message_query["$or"] = [
                        {"metadata.analysis_type": "individual"},
                        {"metadata.analysis_type": None},
                        {"metadata.analysis_type": {"$exists": False}},
                    ]
                else:
                    # For "portfolio", exact match only
                    message_query["metadata.analysis_type"] = analysis_type

            # For Portfolio Decisions chat with symbol filter, filter by symbols_analyzed
            if is_portfolio_decisions_chat and symbol:
                message_query["metadata.raw_data.symbols_analyzed"] = symbol

            # Get messages for this chat (filtered by date and analysis_type if specified)
            # Sort newest first (most recent analysis at top)
            messages = (
                await messages_collection.find(message_query)
                .sort("timestamp", -1)
                .to_list(length=None)
            )  # Sort newest first

            # Skip chats with no messages matching the filters
            if (date or analysis_type) and not messages:
                continue

            # Clean messages
            for msg in messages:
                msg.pop("_id", None)

            # Get most recent message timestamp for sorting (first message since sorted newest first)
            latest_timestamp = (
                messages[0].get("timestamp", datetime.min) if messages else datetime.min
            )

            result_chats.append(
                {
                    "chat_id": chat_id,
                    "symbol": chat_symbol,  # None for "Portfolio Decisions" chat
                    "title": title,
                    "message_count": len(messages),
                    "messages": messages,
                    "latest_timestamp": (
                        latest_timestamp.isoformat()
                        if isinstance(latest_timestamp, datetime)
                        else str(latest_timestamp)
                    ),
                }
            )

        # Sort chats by most recent message (newest first)
        result_chats.sort(key=lambda c: c.get("latest_timestamp", ""), reverse=True)

        logger.info(
            "Portfolio chat history retrieved",
            chats_count=len(result_chats),
            total_messages=sum(c["message_count"] for c in result_chats),
            date_filter=date,
            analysis_type_filter=analysis_type,
            filtered=bool(date or analysis_type),
        )

        return {"chats": result_chats}

    except Exception as e:
        logger.error(
            "Failed to fetch portfolio chat history",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve portfolio chat history. Please try again later.",
        ) from e


@router.get("/chats/{chat_id}")
@limiter.limit("60/minute")  # Standard read operation
async def get_portfolio_chat_detail(
    request: Request,
    chat_id: str,
    limit: int | None = None,
    chat_service: ChatService = Depends(get_chat_service),
) -> dict:
    """
    Get portfolio agent chat detail with messages.

    Args:
        chat_id: Chat identifier
        limit: Optional message limit (default: 100)

    Returns:
        Chat detail with messages
    """
    try:
        chat = await chat_service.get_chat(chat_id)

        messages = await chat_service.get_chat_messages(chat_id, limit=limit)

        logger.info(
            "Portfolio chat detail retrieved",
            chat_id=chat_id,
            message_count=len(messages),
        )

        return {
            "chat": chat,
            "messages": messages,
        }

    except Exception as e:
        logger.error(
            "Failed to get portfolio chat detail",
            chat_id=chat_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve portfolio chat. Please try again later.",
        ) from e


@router.delete("/chats/{chat_id}", status_code=204)
@limiter.limit("30/minute")  # Write operation - admin only
async def delete_portfolio_chat(
    request: Request,
    chat_id: str,
    _: None = Depends(require_admin),  # Admin only
    chat_service: ChatService = Depends(get_chat_service),
) -> None:
    """
    Delete a portfolio agent chat and all its messages.

    **Admin only** - Requires admin privileges to delete portfolio analysis chats.

    Args:
        chat_id: Chat identifier

    Returns:
        204 No Content on success

    Raises:
        HTTPException: 403 if not admin, 404 if chat not found
    """
    try:
        # Delete chat with portfolio_agent as owner
        deleted = await chat_service.delete_chat(chat_id)

        if not deleted:
            logger.warning(
                "Portfolio chat not found for deletion",
                chat_id=chat_id,
            )
            raise HTTPException(
                status_code=404,
                detail="Portfolio chat not found",
            )

        logger.info(
            "Portfolio chat deleted",
            chat_id=chat_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete portfolio chat",
            chat_id=chat_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to delete portfolio chat. Please try again later.",
        ) from e
