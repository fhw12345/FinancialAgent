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

        # Build result: ONE CARD PER MESSAGE.
        #
        # Old behaviour grouped messages under their parent chat ("Portfolio
        # Decisions" or "<SYMBOL> Analysis"), so 12 reruns of portfolio
        # analysis collapsed into 1 sidebar card. Users expect one card per
        # analysis run, so we now flatten: each portfolio/analysis message
        # becomes its own card. The frontend's chat_id/messages contract is
        # preserved by mapping `chat_id := message_id` and putting the
        # single message into a one-element `messages` list.
        #
        # The DELETE /chats/{chat_id} route below was updated alongside this
        # to interpret chat_id as a message_id when it starts with "msg_".
        result_chats: list[dict] = []

        for chat in portfolio_chats:
            chat_id = chat["chat_id"]
            title = chat.get("title", "Unknown")
            is_portfolio_decisions_chat = title == "Portfolio Decisions"

            # Build message query
            message_query: dict = {"chat_id": chat_id}
            if date_start and date_end:
                message_query["timestamp"] = {"$gte": date_start, "$lt": date_end}
            elif date_start:
                message_query["timestamp"] = {"$gte": date_start}
            elif date_end:
                message_query["timestamp"] = {"$lt": date_end}

            # Filter by analysis_type if specified
            if analysis_type:
                if analysis_type == "individual":
                    # Match "individual" OR null/missing (backward compat)
                    message_query["$or"] = [
                        {"metadata.analysis_type": "individual"},
                        {"metadata.analysis_type": None},
                        {"metadata.analysis_type": {"$exists": False}},
                    ]
                else:
                    message_query["metadata.analysis_type"] = analysis_type

            # For Portfolio Decisions chat with symbol filter, scope to runs
            # that analyzed that symbol.
            if is_portfolio_decisions_chat and symbol:
                message_query["metadata.raw_data.symbols_analyzed"] = symbol

            # Newest first so the chronological-newest card appears first.
            messages = (
                await messages_collection.find(message_query)
                .sort("timestamp", -1)
                .to_list(length=None)
            )
            for msg in messages:
                msg.pop("_id", None)

            for msg in messages:
                msg_id = msg.get("message_id") or ""
                msg_meta = msg.get("metadata") or {}
                msg_ts = msg.get("timestamp", datetime.min)
                ts_iso = (
                    msg_ts.isoformat()
                    if isinstance(msg_ts, datetime)
                    else str(msg_ts)
                )

                # Card title — most informative first:
                #   1. analyzed symbols + time (portfolio decisions)
                #   2. parent chat title + time (single-symbol analysis)
                if is_portfolio_decisions_chat:
                    syms = (msg_meta.get("raw_data") or {}).get(
                        "symbols_analyzed"
                    ) or []
                    sym_str = ", ".join(syms[:3]) if syms else "Portfolio"
                    if len(syms) > 3:
                        sym_str += f" +{len(syms) - 3}"
                    time_str = (
                        msg_ts.strftime("%H:%M")
                        if isinstance(msg_ts, datetime)
                        else ""
                    )
                    card_title = (
                        f"Analysis · {sym_str} · {time_str}"
                        if time_str
                        else f"Analysis · {sym_str}"
                    )
                    card_symbol = syms[0] if len(syms) == 1 else None
                else:
                    parent_symbol = (
                        title.split(" ")[0] if " " in title else title
                    )
                    time_str = (
                        msg_ts.strftime("%H:%M")
                        if isinstance(msg_ts, datetime)
                        else ""
                    )
                    card_title = (
                        f"{parent_symbol} · {time_str}"
                        if time_str
                        else parent_symbol
                    )
                    card_symbol = parent_symbol

                result_chats.append(
                    {
                        # chat_id contract preserved; frontend uses it as
                        # React key + DELETE target. The trailing message_id
                        # makes each card unique even when many cards share
                        # the same parent chat.
                        "chat_id": msg_id or chat_id,
                        "parent_chat_id": chat_id,
                        "symbol": card_symbol,
                        "title": card_title,
                        "message_count": 1,
                        "messages": [msg],
                        "latest_timestamp": ts_iso,
                    }
                )

        # Sort cards globally by their (single) message timestamp, newest first.
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
    mongodb: MongoDB = Depends(get_mongodb),
) -> dict:
    """
    Get portfolio analysis card detail.

    Cards are now per-message (one analysis run = one card). When chat_id
    starts with `msg_`, we look up that single message and return it
    alongside its parent chat. Otherwise we fall back to the legacy
    chat-level fetch (returns the whole chat with up to `limit` messages).
    """
    try:
        # Per-message detail path — what the sidebar uses now.
        if chat_id.startswith("msg_"):
            messages_coll = mongodb.get_collection("messages")
            msg = await messages_coll.find_one({"message_id": chat_id})
            if not msg:
                raise HTTPException(
                    status_code=404,
                    detail="Portfolio analysis card not found",
                )
            msg.pop("_id", None)
            chat = await chat_service.get_chat(msg["chat_id"])
            logger.info(
                "Portfolio analysis card retrieved",
                message_id=chat_id,
                parent_chat_id=msg.get("chat_id"),
            )
            return {"chat": chat, "messages": [msg]}

        # Legacy: full chat with all messages.
        chat = await chat_service.get_chat(chat_id)
        messages = await chat_service.get_chat_messages(chat_id, limit=limit)
        logger.info(
            "Portfolio chat detail retrieved",
            chat_id=chat_id,
            message_count=len(messages),
        )
        return {"chat": chat, "messages": messages}

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
    mongodb: MongoDB = Depends(get_mongodb),
) -> None:
    """
    Delete a portfolio analysis card.

    Cards are now per-message (one analysis run = one card), so the path
    parameter is interpreted as a `message_id` whenever it starts with
    `msg_`. Falls back to deleting the entire chat (legacy behaviour) for
    any other id shape — keeps the route safe for direct chat-level
    cleanups via the API.

    **Admin only**.
    """
    try:
        # Per-message delete path — what the sidebar uses now.
        if chat_id.startswith("msg_"):
            messages_coll = mongodb.get_collection("messages")
            result = await messages_coll.delete_one({"message_id": chat_id})
            if result.deleted_count == 0:
                logger.warning(
                    "Portfolio analysis card not found for deletion",
                    message_id=chat_id,
                )
                raise HTTPException(
                    status_code=404,
                    detail="Portfolio analysis card not found",
                )
            logger.info("Portfolio analysis card deleted", message_id=chat_id)
            return

        # Legacy: delete the whole chat.
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
        logger.info("Portfolio chat deleted", chat_id=chat_id)

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
