"""Local portfolio API router."""

from fastapi import APIRouter

from .assessments import router as assessments_router
from .chats import router as chats_router
from .decisions import router as decisions_router
from .evidence import router as evidence_router
from .holdings import router as holdings_router
from .orders import router as orders_router
from .risk import router as risk_router
from .strategies import router as strategies_router
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
router.include_router(assessments_router)
router.include_router(risk_router)
router.include_router(evidence_router)
router.include_router(strategies_router)
router.include_router(user_transactions_router)

__all__ = ["router"]
