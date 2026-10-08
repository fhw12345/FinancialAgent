"""Golden manual PAPER arithmetic and strict finite/precision/authority boundaries."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.models.paper_ledger import CreatePaper, TradeInput
from src.services.paper_ledger import service, store
from tests.paper_fixtures import action, creation, journal, refresh, setup


@pytest.mark.asyncio
async def test_roundtrip_slippage_golden_no_broker_ledger_mutations(monkeypatch):
    db = setup(monkeypatch)
    made = await service.create(db, creation())
    identifier = made.experiment.experiment_id
    bought = await service.journal(db, identifier, journal(1))
    assert bought.projection.cash == Decimal("8999.00")
    assert bought.trade_receipts[0].effective_price == Decimal("100.10")
    assert bought.valuation is None and bought.ai_validated is False
    marked = await service.refresh(db, identifier, refresh(2))
    assert marked.valuation.nav == Decimal("9999.00")
    sold = await service.journal(
        db, identifier, journal(3, "paper-sell", side="sell", reference_price="110")
    )
    assert sold.projection.cash == Decimal("10097.90")
    assert sold.projection.realized_pnl == Decimal("97.90")
    assert sold.projection.positions == []
    assert (
        sold.valuation.stale and "PAPER_LEDGER_CHANGED" in sold.valuation.stale_reasons
    )
    await service.refresh(db, identifier, refresh(4, "cash-only-refresh"))
    assert db.get_collection("holdings").rows == {}
    assert db.get_collection("user_transactions").rows == {}
    assert db.get_collection("user_settings").rows == {}
    assert db.get_collection("review_control").rows == {}


@pytest.mark.asyncio
async def test_fifo_fee_basis_and_exact_fractional_residual_depletion(monkeypatch):
    db = setup(monkeypatch)
    made = await service.create(db, creation(slippage_bps="0", commission_bps="10"))
    identifier = made.experiment.experiment_id
    bought = await service.journal(
        db, identifier, journal(1, quantity="0.3", reference_price="10")
    )
    assert bought.projection.cash == Decimal("9997.00")  # 0.003 fee rounds to 0 cents
    assert bought.projection.lots[0].cost_basis == Decimal("3.00")
    await service.journal(
        db, identifier, journal(2, "buy-second", quantity="1", reference_price="20")
    )
    part = await service.journal(
        db,
        identifier,
        journal(3, "sell-part", side="sell", quantity="0.1", reference_price="15"),
    )
    assert part.projection.lots[0].quantity == Decimal("0.2")
    assert part.projection.lots[0].cost_basis == Decimal("2.00")
    last = await service.journal(
        db,
        identifier,
        journal(4, "sell-last", side="sell", quantity="0.2", reference_price="15"),
    )
    assert len(last.projection.lots) == 1 and last.projection.lots[
        0
    ].quantity == Decimal("1")
    assert last.projection.realized_pnl == Decimal("1.50")
    done = await service.journal(
        db,
        identifier,
        journal(5, "sell-second", side="sell", quantity="1", reference_price="25"),
    )
    assert done.projection.cash == Decimal("10006.46")
    assert done.projection.realized_pnl == Decimal("6.46")
    assert done.projection.commissions == Decimal("0.04")  # 0.025 ties-to-even → 0.02
    assert not done.projection.lots


@pytest.mark.asyncio
async def test_partial_fifo_cent_rounding_takes_last_basis_residual(monkeypatch):
    db = setup(monkeypatch)
    identifier = (
        await service.create(db, creation(slippage_bps="0"))
    ).experiment.experiment_id
    await service.journal(
        db, identifier, journal(1, quantity="0.3", reference_price="3.333333")
    )
    for index in range(3):
        result = await service.journal(
            db,
            identifier,
            journal(
                index + 2,
                f"sell-fraction-{index}",
                side="sell",
                quantity="0.1",
                reference_price="5",
            ),
        )
    assert result.projection.positions == [] and result.projection.cash == Decimal(
        "10000.50"
    )
    assert result.projection.realized_pnl == Decimal("0.50")


@pytest.mark.asyncio
async def test_manual_split_dividend_mark_drop_no_double_count(monkeypatch):
    db = setup(monkeypatch)
    identifier = (
        await service.create(db, creation(slippage_bps="0"))
    ).experiment.experiment_id
    await service.journal(
        db, identifier, journal(1, quantity="100", reference_price="10")
    )
    split = await service.journal(
        db,
        identifier,
        action(
            2,
            "manual-split",
            {"kind": "split", "symbol": "AAPL", "numerator": 2, "denominator": 1},
        ),
    )
    assert split.projection.positions[0].quantity == Decimal("200")
    assert split.projection.positions[0].cost_basis == Decimal("1000")
    assert split.projection.cash == Decimal("9000")
    dividend = await service.journal(
        db,
        identifier,
        action(
            3,
            "manual-dividend",
            {
                "kind": "dividend",
                "symbol": "AAPL",
                "gross_per_share": "1",
                "withholding": "0",
            },
        ),
    )
    assert dividend.projection.cash == Decimal(
        "9200"
    ) and dividend.projection.dividend_income == Decimal("200")
    from tests.review_fixtures import market_asset

    service.valuation.provider.fetch_asset.side_effect = (
        lambda symbol, session: market_asset(symbol).model_copy(update={"mark": 4.0})
    )
    valued = await service.refresh(db, identifier, refresh(4))
    assert valued.valuation.nav == Decimal("10000")
    assert valued.valuation.scenario_pnl == Decimal("0")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry,code",
    [
        ({"side": "sell", "quantity": "1"}, "PAPER_OVERSELL"),
        ({"symbol": "NVDA"}, "PAPER_SYMBOL_NOT_ALLOWED"),
        ({"quantity": "100"}, "PAPER_CASH_INSUFFICIENT"),
        ({"quantity": "0.000001", "reference_price": "0.000001"}, "TRADE_BELOW_CENT"),
        (
            {"quantity": "1000000000", "reference_price": "1000000000"},
            "MONEY_RANGE_EXCEEDED",
        ),
    ],
)
async def test_bad_trades_never_commit(monkeypatch, entry, code):
    db = setup(monkeypatch)
    identifier = (await service.create(db, creation())).experiment.experiment_id
    with pytest.raises(store.PaperConflict, match=code):
        await service.journal(db, identifier, journal(1, **entry))
    assert (await service.get(db, identifier)).experiment.sequence == 1


@pytest.mark.parametrize(
    "value",
    [
        True,
        1,
        0.1,
        float("inf"),
        "NaN",
        "Infinity",
        "1e3",
        "-1",
        "01",
        "1.0000001",
        "",
        "1000000001",
    ],
)
def test_decimal_wire_requires_plain_finite_strings(value):
    with pytest.raises(ValidationError):
        TradeInput(symbol="AAPL", side="buy", quantity=value, reference_price="1")


def test_money_precision_permission_identity_and_time_are_not_forged():
    with pytest.raises(ValidationError):
        creation(initial_cash="1.001")
    with pytest.raises(ValidationError):
        creation(symbols=["AAPL", "AAPL"])
    for extra in (
        {"approval_id": "x"},
        {"ready": True},
        {"executed_at": "2020-01-01"},
        {"side": "short"},
    ):
        with pytest.raises(ValidationError):
            TradeInput.model_validate(
                {
                    "symbol": "AAPL",
                    "side": "buy",
                    "quantity": "1",
                    "reference_price": "1",
                    **extra,
                }
            )
    payload = creation().model_dump(mode="json")
    for confirmation in (False, 1, "true"):
        with pytest.raises(ValidationError):
            CreatePaper.model_validate({**payload, "confirm": confirmation})
