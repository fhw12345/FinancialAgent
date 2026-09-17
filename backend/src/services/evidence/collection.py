"""Collect through existing providers once, seal before models run, and reuse sealed retries."""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from ...database.repositories.evidence_repository import EvidenceRepository
from ...models.evidence import EvidenceRecord, EvidenceSnapshot
from ...models.portfolio_risk import PortfolioRiskSnapshot
from ...services.data_manager.types import Granularity
from . import adapters


async def collect(
    repository: EvidenceRepository,
    *,
    request_key: str,
    run_id: str,
    symbol: str,
    as_of: datetime,
    data_manager: Any,
    market_service: Any,
    risk: PortfolioRiskSnapshot | None = None,
) -> EvidenceSnapshot:
    snapshot = await repository.begin(
        request_key=request_key,
        run_id=run_id,
        symbol=symbol,
        as_of=as_of,
        risk_snapshot_id=risk.snapshot_id if risk else None,
        policy_revision=risk.policy.revision if risk else None,
    )
    if snapshot.state == "sealed":
        return snapshot

    async def safe(coroutine: Any, default: Any) -> Any:
        try:
            return await asyncio.wait_for(coroutine, timeout=12)
        except Exception:
            return default

    try:
        # No second provider chain: DataManager/market service retain their existing
        # provider order and Redis fallback semantics (including failed-call dedup).
        quote, overview, cash, balance, bars, news, filing = await asyncio.gather(
            safe(data_manager.get_quote(symbol), None),
            safe(market_service.get_company_overview(symbol), {}),
            safe(market_service.get_cash_flow(symbol), {}),
            safe(market_service.get_balance_sheet(symbol), {}),
            safe(
                data_manager.get_ohlcv(
                    symbol,
                    Granularity.DAILY,
                    start_date=(as_of - timedelta(days=100)).date().isoformat(),
                    end_date=as_of.date().isoformat(),
                ),
                [],
            ),
            safe(
                data_manager.get_company_news(
                    symbol,
                    (as_of - timedelta(days=7)).date().isoformat(),
                    as_of.date().isoformat(),
                ),
                [],
            ),
            safe(data_manager.get_insider_trades(symbol), []),
        )
        if overview.get("Symbol", symbol).upper() != symbol:
            overview = {}
        currency = overview.get("Currency")
        records: list[EvidenceRecord] = []
        for build in [
            lambda: adapters.quote(snapshot, quote, currency, risk),
            lambda: adapters.overview(snapshot, overview),
            lambda: adapters.statements(snapshot, "cash_flow", cash),
            lambda: adapters.statements(snapshot, "balance_sheet", balance),
            lambda: adapters.ohlcv(snapshot, bars, currency),
            lambda: adapters.news(snapshot, news),
            lambda: adapters.filings(snapshot, filing),
        ]:
            records.extend(build())
        return await repository.finish(snapshot, records)
    except asyncio.CancelledError:
        await repository.abort(snapshot, "COLLECTION_CANCELLED", True)
        raise
    except Exception:
        await repository.abort(snapshot, "COLLECTION_FAILED")
        raise
