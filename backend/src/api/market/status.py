"""
Market status and hours endpoints.

Handles market open/close status and trading session information.
"""

from datetime import timedelta

import pandas as pd
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...services.alphavantage_market_data import get_market_session

router = APIRouter()
logger = structlog.get_logger()


class MarketStatusResponse(BaseModel):
    """Market status response."""

    is_open: bool = Field(
        ..., description="Whether market is currently open for trading"
    )
    current_session: str = Field(
        ..., description="Current market session: pre, regular, post, or closed"
    )
    next_open: str | None = Field(
        None, description="Next market open time (ISO format)"
    )
    next_close: str | None = Field(
        None, description="Next market close time (ISO format)"
    )
    timestamp: str = Field(..., description="Current timestamp (ISO format)")


@router.get("/status", response_model=MarketStatusResponse)
async def get_market_status() -> MarketStatusResponse:
    """
    Get current market status (open/closed, current session).

    Returns real-time market hours status for UI controls and intraday trading restrictions.

    Market hours (US Eastern Time):
    - Pre-market: 4:00 AM - 9:30 AM
    - Regular: 9:30 AM - 4:00 PM
    - Post-market: 4:00 PM - 8:00 PM
    - Closed: 8:00 PM - 4:00 AM, weekends
    """
    try:
        # Get current time in Eastern Time
        now = pd.Timestamp.now(tz="America/New_York")

        # Get current session
        current_session = get_market_session(now)
        is_open = current_session in ["pre", "regular", "post"]

        # Calculate next open/close times
        next_open = None
        next_close = None

        if current_session == "closed":
            # If closed, calculate when market opens next
            # If weekend, next open is Monday 4:00 AM ET
            # If weeknight (after 8 PM), next open is tomorrow 4:00 AM ET
            if now.weekday() >= 5:  # Weekend
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0:
                    days_until_monday = 1  # If Sunday, next Monday
                next_open_dt = now + timedelta(days=days_until_monday)
                next_open_dt = next_open_dt.replace(
                    hour=4, minute=0, second=0, microsecond=0
                )
            else:  # Weeknight
                next_open_dt = now + timedelta(days=1)
                next_open_dt = next_open_dt.replace(
                    hour=4, minute=0, second=0, microsecond=0
                )

            next_open = next_open_dt.isoformat()

        elif current_session == "pre":
            # Pre-market: next close is 9:30 AM (when regular opens)
            # But we consider "close" as market close at 4 PM
            next_close_dt = now.replace(hour=16, minute=0, second=0, microsecond=0)
            next_close = next_close_dt.isoformat()

        elif current_session == "regular":
            # Regular hours: next close is 4:00 PM
            next_close_dt = now.replace(hour=16, minute=0, second=0, microsecond=0)
            next_close = next_close_dt.isoformat()

        elif current_session == "post":
            # Post-market: next close is 8:00 PM
            next_close_dt = now.replace(hour=20, minute=0, second=0, microsecond=0)
            next_close = next_close_dt.isoformat()

        logger.info(
            "Market status checked",
            current_session=current_session,
            is_open=is_open,
        )

        return MarketStatusResponse(
            is_open=is_open,
            current_session=current_session,
            next_open=next_open,
            next_close=next_close,
            timestamp=now.isoformat(),
        )

    except Exception as e:
        logger.error(
            "Market status check failed", error=str(e), error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to check market status: {str(e)}"
        ) from e
