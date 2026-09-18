"""IDQ-002 acceptance: fixed clock, actual API/graph/provider adapter/storage."""

from datetime import UTC, datetime
from src.services.portfolio_risk import service
from src.services import agent_run_service
from src.api import portfolio_admin
from tests.e2e.decision_policy_app import app, reset


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 16, 21, 0, tzinfo=UTC)


service.datetime = Clock
agent_run_service.utcnow = lambda: Clock.now(UTC)
portfolio_admin.utcnow = lambda: Clock.now(UTC)


@app.post("/api/test/risk/reset")
async def reset_risk():
    await reset("good")
    await app.state.mongodb.get_collection("holdings").update_one(
        {"symbol": "AAPL"},
        {
            "$set": {
                "quantity": 0.5,
                "avg_price": 90.0,
                "cost_basis": 45.0,
                "market_value": 50.0,
            }
        },
    )
    await app.state.mongodb.get_collection("user_settings").update_one(
        {}, {"$set": {"cash_balance": 450.0}}
    )
    return {"reset": True}
