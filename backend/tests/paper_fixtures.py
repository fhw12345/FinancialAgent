"""Synthetic user scenario parameters, clock and outer market; production journal is real."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from src.models.paper_ledger import CreatePaper, JournalPaper, RefreshPaper
from src.services.paper_ledger import service, store, valuation
from tests.evidence_fixtures import Database
from tests.review_fixtures import market_asset

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)


class Clock(datetime):
    value = NOW

    @classmethod
    def now(cls, tz=None):
        return cls.value if tz else cls.value.replace(tzinfo=None)


def setup(monkeypatch):
    Clock.value = NOW
    for module in (service, store, valuation):
        monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(
        valuation.provider,
        "fetch_asset",
        AsyncMock(side_effect=lambda symbol, session: market_asset(symbol)),
    )
    db = Database()
    db.now = NOW
    return db


def creation(**changes):
    return CreatePaper.model_validate(
        {
            "request_id": "paper-create",
            "confirm": True,
            "acknowledgment": "manual-paper-only-no-real-account-or-ai-approval",
            "settings": {
                "name": "Synthetic PAPER",
                "initial_cash": "10000.00",
                "symbols": ["AAPL", "MSFT"],
                "commission_bps": "0",
                "slippage_bps": "10",
                **changes,
            },
        }
    )


def journal(sequence, identifier="paper-trade", **entry):
    return JournalPaper.model_validate(
        {
            "request_id": identifier,
            "expected_sequence": sequence,
            "confirm": True,
            "acknowledgment": "manual-scenario-not-ai-approved-or-market-fill",
            "entry": {
                "kind": "trade",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": "10",
                "reference_price": "100",
                **entry,
            },
        }
    )


def refresh(sequence, identifier="paper-refresh"):
    return RefreshPaper.model_validate(
        {
            "request_id": identifier,
            "expected_sequence": sequence,
            "confirm": True,
            "acknowledgment": "manual-scenario-not-ai-approved-or-market-fill",
            "session_date": "2026-09-17",
            "reconciliation": "corporate-actions-inspected-through-this-session",
        }
    )


def action(sequence, identifier, entry):
    return JournalPaper.model_validate(
        {
            "request_id": identifier,
            "expected_sequence": sequence,
            "confirm": True,
            "acknowledgment": "manual-scenario-not-ai-approved-or-market-fill",
            "entry": entry,
        }
    )
