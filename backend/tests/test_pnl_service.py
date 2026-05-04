"""Unit tests for pnl_service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.portfolio import PortfolioOrder
from src.services.pnl_service import (
    DEFAULT_HORIZONS_DAYS,
    compute_pnl_pct,
    run_pnl_snapshot_job,
    snapshot_decision,
)


def _order(
    side: str = "buy", decision_price: float = 100.0, age_days: int = 10
) -> PortfolioOrder:
    return PortfolioOrder(
        order_id=f"order_{side}_{int(decision_price)}",
        chat_id="c",
        message_id="m",
        alpaca_order_id=None,
        analysis_id="a",
        symbol="AAPL",
        order_type="market",
        side=side,
        quantity=1.0 if side != "hold" else 0.0,
        status="suggested" if side != "hold" else "signal",
        filled_qty=0.0,
        filled_avg_price=None,
        created_at=datetime.now(UTC) - timedelta(days=age_days),
        decision_price=decision_price,
        decision_type="order" if side != "hold" else "signal",
    )


class TestComputePnlPct:
    def test_buy_up_is_positive(self):
        assert compute_pnl_pct("buy", 100.0, 110.0) == pytest.approx(10.0)

    def test_buy_down_is_negative(self):
        assert compute_pnl_pct("buy", 100.0, 90.0) == pytest.approx(-10.0)

    def test_sell_down_is_positive(self):
        # SELL was right when price dropped after the call
        assert compute_pnl_pct("sell", 100.0, 90.0) == pytest.approx(10.0)

    def test_sell_up_is_negative(self):
        assert compute_pnl_pct("sell", 100.0, 110.0) == pytest.approx(-10.0)

    def test_hold_treated_as_buy(self):
        assert compute_pnl_pct("hold", 100.0, 105.0) == pytest.approx(5.0)

    def test_zero_decision_price_returns_zero(self):
        assert compute_pnl_pct("buy", 0.0, 110.0) == 0.0


class TestSnapshotDecision:
    @pytest.mark.asyncio
    async def test_writes_snapshot_on_success(self):
        order = _order(side="buy", decision_price=100.0, age_days=10)
        dm = MagicMock()
        dm.get_price_on_date = AsyncMock(return_value=110.0)
        repo = MagicMock()
        repo.update_pnl_snapshot = AsyncMock(return_value=True)

        snap = await snapshot_decision(
            order, horizon_days=7, data_manager=dm, repo=repo
        )

        assert snap is not None
        assert snap["price"] == 110.0
        assert snap["pnl_pct"] == pytest.approx(10.0)
        repo.update_pnl_snapshot.assert_awaited_once()
        args = repo.update_pnl_snapshot.call_args
        assert args.args[0] == order.order_id
        assert args.args[1] == 7

    @pytest.mark.asyncio
    async def test_skips_when_horizon_not_elapsed(self):
        order = _order(age_days=2)  # 7d horizon not yet reached
        dm = MagicMock()
        dm.get_price_on_date = AsyncMock(return_value=999.0)
        repo = MagicMock()
        repo.update_pnl_snapshot = AsyncMock()

        snap = await snapshot_decision(
            order, horizon_days=7, data_manager=dm, repo=repo
        )

        assert snap is None
        dm.get_price_on_date.assert_not_awaited()
        repo.update_pnl_snapshot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_price_unavailable(self):
        order = _order(age_days=10)
        dm = MagicMock()
        dm.get_price_on_date = AsyncMock(return_value=None)
        repo = MagicMock()
        repo.update_pnl_snapshot = AsyncMock()

        snap = await snapshot_decision(
            order, horizon_days=7, data_manager=dm, repo=repo
        )

        assert snap is None
        repo.update_pnl_snapshot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_no_decision_price(self):
        order = _order(decision_price=0.0, age_days=10)
        dm = MagicMock()
        dm.get_price_on_date = AsyncMock()
        repo = MagicMock()

        snap = await snapshot_decision(
            order, horizon_days=7, data_manager=dm, repo=repo
        )

        assert snap is None
        dm.get_price_on_date.assert_not_awaited()


class TestRunPnlSnapshotJob:
    @pytest.mark.asyncio
    async def test_runs_all_horizons(self):
        order = _order(age_days=100)
        dm = MagicMock()
        dm.get_price_on_date = AsyncMock(return_value=110.0)
        repo = MagicMock()
        repo.list_pending_pnl_snapshots = AsyncMock(return_value=[order])
        repo.update_pnl_snapshot = AsyncMock(return_value=True)

        counters = await run_pnl_snapshot_job(data_manager=dm, repo=repo)

        # Default horizons all process the one pending order
        assert counters == {f"{h}d": 1 for h in DEFAULT_HORIZONS_DAYS}
        assert repo.list_pending_pnl_snapshots.await_count == len(DEFAULT_HORIZONS_DAYS)
        assert repo.update_pnl_snapshot.await_count == len(DEFAULT_HORIZONS_DAYS)

    @pytest.mark.asyncio
    async def test_idempotent_when_no_pending(self):
        dm = MagicMock()
        dm.get_price_on_date = AsyncMock()
        repo = MagicMock()
        repo.list_pending_pnl_snapshots = AsyncMock(return_value=[])
        repo.update_pnl_snapshot = AsyncMock()

        counters = await run_pnl_snapshot_job(data_manager=dm, repo=repo)

        assert all(v == 0 for v in counters.values())
        repo.update_pnl_snapshot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_one_failure_does_not_abort_rest(self):
        good = _order(age_days=100)
        good.order_id = "good"
        bad = _order(age_days=100)
        bad.order_id = "bad"
        dm = MagicMock()
        dm.get_price_on_date = AsyncMock(
            side_effect=[Exception("boom"), 105.0, 110.0, 120.0]
        )
        repo = MagicMock()
        repo.list_pending_pnl_snapshots = AsyncMock(return_value=[bad, good])
        repo.update_pnl_snapshot = AsyncMock(return_value=True)

        counters = await run_pnl_snapshot_job(data_manager=dm, repo=repo, horizons=(7,))

        # bad raised, good wrote → 1 success
        assert counters["7d"] == 1
