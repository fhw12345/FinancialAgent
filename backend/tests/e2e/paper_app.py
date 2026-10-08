"""Manual PAPER browser acceptance: real app/storage, recorded outer prices and faults only."""

from datetime import timedelta

import yfinance as yf
from motor.motor_asyncio import AsyncIOMotorCollection

from src.services.paper_ledger import service, store, valuation
from tests.e2e import evidence_app as evidence
from tests.e2e import review_app as review

app = review.app
mode = "normal"
fault = "none"
market_requests = 0
original_write = AsyncIOMotorCollection.find_one_and_update

for module in (service, store, valuation):
    module.datetime = evidence.Clock


class PaperTicker(review.ReviewTicker):
    def history(self, **kwargs):
        global market_requests
        if kwargs.get("auto_adjust") is False:
            market_requests += 1
            if mode == "missing" and self.symbol == "MSFT":
                raise RuntimeError("Recorded missing price")
        frame = super().history(**kwargs)
        if kwargs.get("auto_adjust") is False and mode in ("split", "dividend"):
            frame["Close"] = 50.0 if mode == "split" else 49.0
        return frame


yf.Ticker = PaperTicker


async def guarded_write(self, *args, **kwargs):
    update = args[1] if len(args) > 1 else kwargs.get("update", {})
    if self.name == store.COLLECTION:
        if fault == "storage" and "$set" in update:
            raise RuntimeError("Recorded paper persistence failure")
        if args and "$expr" in args[0]:
            query = dict(args[0])
            comparison = query["$expr"]["$lt"]
            assert comparison[0] == "$$NOW"
            offset = timedelta(days=7) if fault == "expiry" else timedelta()
            # Record only the Mongo clock operand. The real full CAS still executes.
            query["$expr"] = {"$lt": [evidence.Clock.now() + offset, comparison[1]]}
            args = (query, *args[1:])
    return await original_write(self, *args, **kwargs)


AsyncIOMotorCollection.find_one_and_update = guarded_write


@app.post("/api/test/paper/reset")
async def reset():
    global mode, fault, market_requests
    mode, fault, market_requests = "normal", "none", 0
    await review.reset("normal")
    await app.state.mongodb.get_collection(store.COLLECTION).delete_many({})
    return {"reset": True}


@app.post("/api/test/paper/market/{value}")
async def change_market(value: str):
    global mode
    assert value in ("normal", "missing", "split", "dividend")
    mode = value
    return {"mode": mode}


@app.post("/api/test/paper/fault/{value}")
async def change_fault(value: str):
    global fault
    assert value in ("none", "storage", "expiry")
    fault = value
    return {"fault": fault}


@app.get("/api/test/paper/audit")
async def audit():
    return {"market_requests": market_requests, "real": await review.audit()}
