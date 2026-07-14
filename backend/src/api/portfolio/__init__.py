"""Local portfolio API router."""

from fastapi import APIRouter

from .chats import router as chats_router
from .decisions import router as decisions_router
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
router.include_router(chats_router)
router.include_router(decisions_router)
router.include_router(user_transactions_router)

__all__ = ["router"]
