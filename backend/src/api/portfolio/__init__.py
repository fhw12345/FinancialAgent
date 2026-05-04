"""
Portfolio API module for Alpaca paper trading integration.

Provides REST API access to portfolio functionality including:
- Holdings: Current positions and account summary from Alpaca
- Transactions: Transaction history from MongoDB (includes failures)
- Orders: Order history from Alpaca API
- History: Portfolio value time series and chat history

All portfolio data comes from Alpaca API (single source of truth).
No manual holdings management - Alpaca handles all positions.

This module aggregates all portfolio sub-routers into a single main router.
Backward compatibility is maintained - you can still import `router` directly:
    from src.api.portfolio import router
"""

from fastapi import APIRouter

from .chats import router as chats_router
from .decisions import router as decisions_router
from .history import router as history_router
from .holdings import router as holdings_router
from .orders import router as orders_router
from .transactions import router as transactions_router
from .user_transactions import router as user_transactions_router

# Create main portfolio router
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# Include all sub-routers
router.include_router(holdings_router)
router.include_router(transactions_router)
router.include_router(orders_router)
router.include_router(history_router)
router.include_router(chats_router)
router.include_router(decisions_router)
router.include_router(user_transactions_router)

# Export router for backward compatibility
__all__ = ["router"]
