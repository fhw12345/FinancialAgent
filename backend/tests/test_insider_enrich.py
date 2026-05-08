"""W3.10 — unit tests for the insider-row Form 4 enrichment helpers.

Covers the four public surfaces of ``insider_enrich``:

* ``enrich_insider_rows`` — date+shares match, RSU fractional-share
  tolerance, no-mutation guarantee, missing-form4 short-circuit.
* ``compute_pct_of_holdings_after`` — happy path, missing legs,
  zero/negative ``shares_owned_after`` guard.
* ``Last12moSummary`` + ``build_last_12mo_summary`` — 365-day window
  bounds, plan_breakdown counts, total_shares aggregation, empty-window
  rendering.
* ``render_enriched_row`` — pre-enrichment rows render exactly like
  W3.5 baseline; enriched rows append ``plan=...`` / ``X% of holdings
  after`` segments.
"""

from __future__ import annotations

from datetime import date

from src.agent.tools.finnhub.insider_enrich import (
    Last12moSummary,
    build_last_12mo_summary,
    compute_pct_of_holdings_after,
    enrich_insider_rows,
    render_enriched_row,
)
from src.agent.tools.sec_edgar.form4 import (
    PLAN_TYPE_10B5_1,
    PLAN_TYPE_DISCRETIONARY,
    PLAN_TYPE_UNKNOWN,
    Form4Transaction,
)


def _tx(
    d: date,
    shares: float,
    *,
    plan: str = PLAN_TYPE_10B5_1,
    after: float | None = 100_000.0,
    adopted: date | None = None,
    code: str = "S",
) -> Form4Transaction:
    return Form4Transaction(
        transaction_date=d,
        transaction_code=code,
        shares=shares,
        share_price=150.0,
        shares_owned_after=after,
        plan_type=plan,
        plan_adopted_date=adopted,
        reporter_name="Doe Jane",
        issuer_symbol="AAPL",
        footnote_ids=(),
    )


# ---------------------------------------------------------------------------
# enrich_insider_rows
# ---------------------------------------------------------------------------

class TestEnrichInsiderRows:
    def test_no_form4_returns_shallow_copies(self) -> None:
        rows = [{"transactionDate": "2025-04-01", "share": 1000}]
        out = enrich_insider_rows(rows, None)
        assert out == rows
        assert out is not rows
        assert out[0] is not rows[0]

    def test_empty_form4_returns_shallow_copies(self) -> None:
        rows = [{"transactionDate": "2025-04-01", "share": 1000}]
        out = enrich_insider_rows(rows, [])
        assert out == rows
        assert out[0] is not rows[0]

    def test_matched_row_merges_plan_and_holdings(self) -> None:
        rows = [{"transactionDate": "2025-04-01", "share": 1000}]
        txs = [
            _tx(date(2025, 4, 1), 1000.0, plan=PLAN_TYPE_10B5_1, after=100_000.0,
                adopted=date(2024, 12, 15))
        ]
        out = enrich_insider_rows(rows, txs)
        r = out[0]
        assert r["plan_type"] == PLAN_TYPE_10B5_1
        assert r["shares_owned_after"] == 100_000.0
        assert r["plan_adopted_date"] == "2024-12-15"
        assert r["pct_of_holdings_after"] == 0.01

    def test_no_mutation_of_input(self) -> None:
        rows = [{"transactionDate": "2025-04-01", "share": 1000}]
        txs = [_tx(date(2025, 4, 1), 1000.0)]
        enrich_insider_rows(rows, txs)
        assert rows == [{"transactionDate": "2025-04-01", "share": 1000}]

    def test_fractional_shares_within_tolerance(self) -> None:
        # Finnhub rounds to 1500; Form 4 carries 1500.5 (RSU vest).
        rows = [{"transactionDate": "2025-04-01", "share": 1500}]
        txs = [_tx(date(2025, 4, 1), 1500.5)]
        out = enrich_insider_rows(rows, txs)
        assert out[0].get("plan_type") == PLAN_TYPE_10B5_1

    def test_share_count_outside_tolerance_does_not_match(self) -> None:
        rows = [{"transactionDate": "2025-04-01", "share": 1000}]
        txs = [_tx(date(2025, 4, 1), 1010.0)]  # diff 10 shares > tol 1
        out = enrich_insider_rows(rows, txs)
        assert "plan_type" not in out[0]

    def test_mismatched_date_does_not_merge(self) -> None:
        rows = [{"transactionDate": "2025-04-01", "share": 1000}]
        txs = [_tx(date(2025, 4, 2), 1000.0)]
        out = enrich_insider_rows(rows, txs)
        assert "plan_type" not in out[0]

    def test_alpha_vantage_shape(self) -> None:
        # AV uses capitalized keys.
        rows = [{"Date": "2025-04-01", "Shares": "2,500"}]
        txs = [_tx(date(2025, 4, 1), 2500.0)]
        out = enrich_insider_rows(rows, txs)
        assert out[0]["plan_type"] == PLAN_TYPE_10B5_1

    def test_yfinance_shape(self) -> None:
        # yfinance DataFrame.to_dict shape.
        rows = [{"Start Date": "2025-04-01", "change": 750.0}]
        txs = [_tx(date(2025, 4, 1), 750.0)]
        out = enrich_insider_rows(rows, txs)
        assert out[0]["plan_type"] == PLAN_TYPE_10B5_1

    def test_skip_first_only_picks_one_match(self) -> None:
        rows = [{"transactionDate": "2025-04-01", "share": 1000}]
        txs = [
            _tx(date(2025, 4, 1), 1000.0, plan=PLAN_TYPE_10B5_1),
            _tx(date(2025, 4, 1), 1000.0, plan=PLAN_TYPE_DISCRETIONARY),
        ]
        out = enrich_insider_rows(rows, txs)
        # First match wins (10b5-1).
        assert out[0]["plan_type"] == PLAN_TYPE_10B5_1

    def test_row_with_unparseable_date_is_passthrough(self) -> None:
        rows = [{"transactionDate": "not-a-date", "share": 1000}]
        txs = [_tx(date(2025, 4, 1), 1000.0)]
        out = enrich_insider_rows(rows, txs)
        assert "plan_type" not in out[0]


# ---------------------------------------------------------------------------
# compute_pct_of_holdings_after
# ---------------------------------------------------------------------------

class TestPctOfHoldingsAfter:
    def test_happy_path(self) -> None:
        row = {"share": 5000, "shares_owned_after": 100_000}
        assert compute_pct_of_holdings_after(row) == 0.05

    def test_missing_shares(self) -> None:
        row = {"shares_owned_after": 100_000}
        assert compute_pct_of_holdings_after(row) is None

    def test_missing_after(self) -> None:
        row = {"share": 5000}
        assert compute_pct_of_holdings_after(row) is None

    def test_zero_after_returns_none(self) -> None:
        row = {"share": 5000, "shares_owned_after": 0}
        assert compute_pct_of_holdings_after(row) is None

    def test_negative_after_returns_none(self) -> None:
        row = {"share": 5000, "shares_owned_after": -10}
        assert compute_pct_of_holdings_after(row) is None

    def test_string_after_value(self) -> None:
        row = {"share": "5,000", "shares_owned_after": "100000"}
        assert compute_pct_of_holdings_after(row) == 0.05

    def test_unparseable_after(self) -> None:
        row = {"share": 5000, "shares_owned_after": "abc"}
        assert compute_pct_of_holdings_after(row) is None


# ---------------------------------------------------------------------------
# Last12moSummary + build_last_12mo_summary
# ---------------------------------------------------------------------------

class TestLast12moSummary:
    def test_empty_renders_no_transactions(self) -> None:
        s = Last12moSummary(transaction_count=0, plan_breakdown={}, total_shares=0.0)
        assert s.render() == "no insider transactions in last 12mo"

    def test_render_includes_count_and_plan_and_shares(self) -> None:
        s = Last12moSummary(
            transaction_count=3,
            plan_breakdown={PLAN_TYPE_10B5_1: 2, PLAN_TYPE_DISCRETIONARY: 1},
            total_shares=12_500.0,
        )
        out = s.render()
        assert "3 tx" in out
        assert "2 10b5-1" in out
        assert "1 discretionary" in out
        assert "12,500 shares total" in out

    def test_window_includes_anchor_and_excludes_pre_cutoff(self) -> None:
        anchor = date(2026, 5, 1)
        txs = [
            _tx(date(2026, 5, 1), 100.0),                      # anchor
            _tx(date(2026, 4, 30), 200.0),                     # 1 day inside
            _tx(date(2025, 5, 2), 300.0),                      # at cutoff edge
            _tx(anchor.replace(year=2024), 999.0),             # 2 yrs prior — out
        ]
        s = build_last_12mo_summary(txs, anchor_date=anchor)
        assert s.transaction_count == 3
        assert s.total_shares == 600.0

    def test_plan_breakdown_counts(self) -> None:
        anchor = date(2026, 5, 1)
        txs = [
            _tx(date(2026, 4, 1), 100.0, plan=PLAN_TYPE_10B5_1),
            _tx(date(2026, 4, 1), 100.0, plan=PLAN_TYPE_10B5_1),
            _tx(date(2026, 3, 1), 100.0, plan=PLAN_TYPE_DISCRETIONARY),
            _tx(date(2026, 2, 1), 100.0, plan=PLAN_TYPE_UNKNOWN),
        ]
        s = build_last_12mo_summary(txs, anchor_date=anchor)
        assert s.plan_breakdown == {
            PLAN_TYPE_10B5_1: 2,
            PLAN_TYPE_DISCRETIONARY: 1,
            PLAN_TYPE_UNKNOWN: 1,
        }

    def test_default_anchor_uses_today(self) -> None:
        # Smoke test: should accept None anchor and not raise.
        s = build_last_12mo_summary([])
        assert s.transaction_count == 0

    def test_drops_tx_without_date(self) -> None:
        anchor = date(2026, 5, 1)
        txs = [_tx(date(2026, 4, 1), 100.0), _tx(date(2026, 4, 1), 50.0)]
        # Forge one with date=None.
        txs[1] = Form4Transaction(
            transaction_date=None,
            transaction_code="S",
            shares=50.0,
            share_price=None,
            shares_owned_after=None,
            plan_type=PLAN_TYPE_UNKNOWN,
            plan_adopted_date=None,
            reporter_name=None,
            issuer_symbol=None,
        )
        s = build_last_12mo_summary(txs, anchor_date=anchor)
        assert s.transaction_count == 1
        assert s.total_shares == 100.0


# ---------------------------------------------------------------------------
# render_enriched_row
# ---------------------------------------------------------------------------

class TestRenderEnrichedRow:
    def test_pre_enrichment_baseline(self) -> None:
        row = {
            "transactionDate": "2025-04-01",
            "name": "Doe Jane",
            "share": 1000,
            "transactionCode": "S",
        }
        out = render_enriched_row(row)
        assert out == "- [2025-04-01] Doe Jane: 1000 shares (S)"

    def test_enriched_row_appends_plan_and_pct(self) -> None:
        row = {
            "transactionDate": "2025-04-01",
            "name": "Doe Jane",
            "share": 5000,
            "transactionCode": "S",
            "plan_type": PLAN_TYPE_10B5_1,
            "shares_owned_after": 100_000,
            "pct_of_holdings_after": 0.05,
        }
        out = render_enriched_row(row)
        assert "plan=10b5-1" in out
        assert "5.0% of holdings after" in out

    def test_unknown_plan_omitted(self) -> None:
        row = {
            "transactionDate": "2025-04-01",
            "name": "Doe Jane",
            "share": 1000,
            "transactionCode": "S",
            "plan_type": PLAN_TYPE_UNKNOWN,
        }
        out = render_enriched_row(row)
        assert "plan=" not in out

    def test_missing_pct_omitted(self) -> None:
        row = {
            "transactionDate": "2025-04-01",
            "name": "Doe Jane",
            "share": 1000,
            "transactionCode": "S",
            "plan_type": PLAN_TYPE_DISCRETIONARY,
        }
        out = render_enriched_row(row)
        assert "of holdings after" not in out
        assert "plan=discretionary" in out

    def test_alpha_vantage_shape(self) -> None:
        row = {"Date": "2025-04-01", "Insider": "Smith John", "Shares": 2500,
               "Transaction": "Sale"}
        out = render_enriched_row(row)
        assert "Smith John" in out
        assert "2025-04-01" in out
        assert "(Sale)" in out
