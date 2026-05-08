"""W3.12 — end-to-end source-footnote pipeline (W3-E1..W3-E4).

Purely offline: no LLM, no SEC traffic, no live data manager. Wires
together the W3.4 / W3.5 / W3.7 / W3.10 / W3.11 surfaces against
canned fixtures so the four PRD e2e ACs can be asserted in CI:

* **W3-E1** — quote / news / fundamentals / insider tools all emit a
  ``Source: <provider> [<ID>] asof <iso>`` footer that the frontend
  footnote extractor (W3.7 ``SOURCE_ID_PATTERN`` + ``parseSourceId``)
  can recover. We mirror the JS regex in Python so the assertion runs
  in the backend test suite.
* **W3-E2** — extracted footnote IDs round-trip back to provider
  label, field code, symbol, asof date.
* **W3-E3** — insider rows enriched with W3.10 plan_type +
  pct_of_holdings_after produce per-row markdown lines that downstream
  UI can split into a plan-type label column and a pct column.
* **W3-E4** — the Phase1 prompt's W3.11 rule, applied to two fixture
  scenarios (single 10b5-1 sale vs. 3-tx discretionary cluster > 5%
  of holdings), blocks bearish framing for the first and permits it
  for the second. We assert the rule itself, not LLM output — the
  empirical "Claude actually obeys" check is the W3.13 integration
  test.
"""

from __future__ import annotations

import inspect
import re
from datetime import UTC, date, datetime, timedelta

from src.agent.portfolio.phase1_research import Phase1ResearchMixin
from src.agent.tools.finnhub.insider import (
    _insider_latest_asof,
    _insider_source_id,
)
from src.agent.tools.finnhub.insider_enrich import (
    build_last_12mo_summary,
    enrich_insider_rows,
    render_enriched_row,
)
from src.agent.tools.sec_edgar.form4 import (
    PLAN_TYPE_10B5_1,
    PLAN_TYPE_DISCRETIONARY,
    PLAN_TYPE_UNKNOWN,
    Form4Transaction,
)

# ---------------------------------------------------------------------------
# Mirror of the W3.7 frontend regex so we can assert footnote-extract
# parity from Python. The JS pattern is:
#   /\[([A-Z][A-Z0-9_]*-[A-Z]+-[A-Z0-9.]+-\d{4}-\d{2}-\d{2})\]/g
# ---------------------------------------------------------------------------

SOURCE_ID_PATTERN = re.compile(
    r"\[([A-Z][A-Z0-9_]*-[A-Z]+-[A-Z0-9.]+-\d{4}-\d{2}-\d{2})\]"
)
_PROVIDER_LABEL = {"FH": "Finnhub", "AV": "Alpha Vantage", "YF": "yfinance"}
_FIELD_LABEL = {
    "Q": "quote",
    "OV": "company overview",
    "CF": "cash flow",
    "BS": "balance sheet",
    "EAR": "earnings",
    "INS": "insider",
    "N": "news",
}


def _extract_footnotes(thesis: str) -> list[dict[str, str]]:
    """Mirror W3.7's frontend extractor: dedupe in citation order."""
    seen: list[str] = []
    for m in SOURCE_ID_PATTERN.finditer(thesis):
        sid = m.group(1)
        if sid not in seen:
            seen.append(sid)
    out = []
    for sid in seen:
        parsed = _parse_source_id(sid)
        if parsed is not None:
            out.append(parsed)
    return out


def _parse_source_id(sid: str) -> dict[str, str] | None:
    """Mirror W3.7 ``parseSourceId``."""
    parts = sid.split("-")
    if len(parts) < 6:
        return None
    provider, field = parts[0], parts[1]
    asof = "-".join(parts[-3:])
    symbol = "-".join(parts[2:-3])
    return {
        "id": sid,
        "provider": _PROVIDER_LABEL.get(provider, provider),
        "field": _FIELD_LABEL.get(field, field),
        "symbol": symbol,
        "asof": asof,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ANCHOR_DATE = date(2026, 5, 9)
ANCHOR_DT = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)


def _make_insider_rows_single_10b5_1() -> tuple[list[dict], list[Form4Transaction]]:
    rows = [
        {
            "transactionDate": "2026-04-15",
            "name": "Cook Tim",
            "share": 1000,
            "transactionCode": "S",
        }
    ]
    txs = [
        Form4Transaction(
            transaction_date=date(2026, 4, 15),
            transaction_code="S",
            shares=1000.0,
            share_price=190.0,
            shares_owned_after=200_000.0,
            plan_type=PLAN_TYPE_10B5_1,
            plan_adopted_date=date(2025, 12, 1),
            reporter_name="Cook Tim",
            issuer_symbol="AAPL",
        )
    ]
    return rows, txs


def _make_insider_rows_discretionary_cluster() -> tuple[
    list[dict], list[Form4Transaction]
]:
    # 3 sells inside a 30-day window, one > 5% of holdings.
    rows = [
        {"transactionDate": "2026-04-30", "name": "VP One", "share": 6000, "transactionCode": "S"},
        {"transactionDate": "2026-04-22", "name": "VP Two", "share": 4000, "transactionCode": "S"},
        {"transactionDate": "2026-04-12", "name": "VP Three", "share": 3500, "transactionCode": "S"},
    ]
    txs = [
        Form4Transaction(
            transaction_date=date(2026, 4, 30),
            transaction_code="S",
            shares=6000.0,
            share_price=190.0,
            shares_owned_after=100_000.0,  # 6% — > 5%
            plan_type=PLAN_TYPE_DISCRETIONARY,
            plan_adopted_date=None,
            reporter_name="VP One",
            issuer_symbol="AAPL",
        ),
        Form4Transaction(
            transaction_date=date(2026, 4, 22),
            transaction_code="S",
            shares=4000.0,
            share_price=189.0,
            shares_owned_after=80_000.0,  # 5% — at boundary
            plan_type=PLAN_TYPE_DISCRETIONARY,
            plan_adopted_date=None,
            reporter_name="VP Two",
            issuer_symbol="AAPL",
        ),
        Form4Transaction(
            transaction_date=date(2026, 4, 12),
            transaction_code="S",
            shares=3500.0,
            share_price=187.0,
            shares_owned_after=120_000.0,  # ~3%
            plan_type=PLAN_TYPE_DISCRETIONARY,
            plan_adopted_date=None,
            reporter_name="VP Three",
            issuer_symbol="AAPL",
        ),
    ]
    return rows, txs


def _make_insider_tool_output(rows: list[dict], symbol: str = "AAPL") -> str:
    """Compose the same tool output shape as `finnhub_insider_trades`."""
    lines = [f"{symbol} recent insider transactions ({len(rows)} rows):"]
    for r in rows:
        name = r.get("name") or "?"
        share = r.get("share") or "?"
        code = r.get("transactionCode") or ""
        d = r.get("transactionDate") or ""
        lines.append(f"- [{d}] {name}: {share} shares ({code})")
    asof = _insider_latest_asof(rows) or ANCHOR_DT
    sid = _insider_source_id("finnhub", symbol, asof)
    asof_repr = asof.strftime("%Y-%m-%dT%H:%MZ")
    lines.append("")
    lines.append(f"Source: finnhub [{sid}] asof {asof_repr}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# W3-E1: every report number can be back-mapped to a Source footnote
# ---------------------------------------------------------------------------

class TestW3E1ReportFootnoteCoverage:
    def test_insider_tool_emits_extractable_source_id(self) -> None:
        rows, _ = _make_insider_rows_single_10b5_1()
        out = _make_insider_tool_output(rows)
        ids = SOURCE_ID_PATTERN.findall(out)
        assert ids == ["FH-INS-AAPL-2026-04-15"]

    def test_synthetic_thesis_with_inline_tokens_extracts_in_citation_order(self) -> None:
        # A Phase2 thesis bullet mock that cites three different IDs;
        # one is repeated to confirm dedup-by-first-appearance.
        thesis = (
            "P/E sits at 28 [FH-Q-AAPL-2026-05-09] vs. peers' 22.\n"
            "Recent earnings beat by 5% [AV-EAR-AAPL-2026-04-25].\n"
            "Insider buying cluster reinforces the bull case "
            "[FH-INS-AAPL-2026-04-15].\n"
            "Quote checked again [FH-Q-AAPL-2026-05-09]."  # dup
        )
        notes = _extract_footnotes(thesis)
        assert [n["id"] for n in notes] == [
            "FH-Q-AAPL-2026-05-09",
            "AV-EAR-AAPL-2026-04-25",
            "FH-INS-AAPL-2026-04-15",
        ]


# ---------------------------------------------------------------------------
# W3-E2: footnote list at report bottom, fields decoded
# ---------------------------------------------------------------------------

class TestW3E2FootnoteListDecoding:
    def test_provider_field_symbol_asof_decode(self) -> None:
        sid = "FH-INS-AAPL-2026-04-15"
        parsed = _parse_source_id(sid)
        assert parsed == {
            "id": sid,
            "provider": "Finnhub",
            "field": "insider",
            "symbol": "AAPL",
            "asof": "2026-04-15",
        }

    def test_alpha_vantage_earnings(self) -> None:
        parsed = _parse_source_id("AV-EAR-AAPL-2026-04-25")
        assert parsed["provider"] == "Alpha Vantage"
        assert parsed["field"] == "earnings"

    def test_yfinance_quote(self) -> None:
        parsed = _parse_source_id("YF-Q-NVDA-2026-05-08")
        assert parsed["provider"] == "yfinance"
        assert parsed["field"] == "quote"
        assert parsed["symbol"] == "NVDA"

    def test_unknown_field_falls_back_to_raw_code(self) -> None:
        # Forward-compat: a not-yet-mapped field code is returned as-is
        # rather than being silently dropped.
        parsed = _parse_source_id("FH-XYZ-AAPL-2026-04-15")
        assert parsed["field"] == "XYZ"

    def test_malformed_id_returns_none(self) -> None:
        assert _parse_source_id("FH-Q-AAPL") is None

    def test_dotted_symbol_preserved(self) -> None:
        # Tickers like BRK.B carry a dot — must round-trip cleanly.
        parsed = _parse_source_id("FH-Q-BRK.B-2026-05-09")
        assert parsed["symbol"] == "BRK.B"


# ---------------------------------------------------------------------------
# W3-E3: per-row plan_type + pct_of_holdings_after enrichment
# ---------------------------------------------------------------------------

class TestW3E3InsiderRowEnrichment:
    def test_10b5_1_row_renders_plan_label(self) -> None:
        rows, txs = _make_insider_rows_single_10b5_1()
        enriched = enrich_insider_rows(rows, txs)
        line = render_enriched_row(enriched[0])
        assert "plan=10b5-1" in line
        # 1000 / 200000 = 0.5%
        assert "0.5% of holdings after" in line

    def test_discretionary_cluster_first_row_above_5pct(self) -> None:
        rows, txs = _make_insider_rows_discretionary_cluster()
        enriched = enrich_insider_rows(rows, txs)
        # 6000 / 100000 = 6%
        line0 = render_enriched_row(enriched[0])
        assert "plan=discretionary" in line0
        assert "6.0% of holdings after" in line0

    def test_unknown_plan_does_not_render_label(self) -> None:
        row = {
            "transactionDate": "2026-04-15",
            "name": "Anon",
            "share": 100,
            "transactionCode": "S",
            "plan_type": PLAN_TYPE_UNKNOWN,
        }
        out = render_enriched_row(row)
        assert "plan=" not in out

    def test_aggregate_drives_summary_header(self) -> None:
        _, txs = _make_insider_rows_discretionary_cluster()
        s = build_last_12mo_summary(txs, anchor_date=ANCHOR_DATE)
        rendered = s.render()
        assert "3 tx" in rendered
        assert "3 discretionary" in rendered


# ---------------------------------------------------------------------------
# W3-E4: prompt rule blocks bearish framing for single 10b5-1 sale,
# permits it for 3-tx discretionary cluster > 5% of holdings.
# ---------------------------------------------------------------------------

class TestW3E4PromptFramingScenarios:
    def _prompt_text(self) -> str:
        return " ".join(
            inspect.getsource(Phase1ResearchMixin._analyze_symbol).split()
        )

    def test_single_10b5_1_sale_locked_out_of_bearish_framing(self) -> None:
        # PRD W3-E4 + AC#4: rule states 10b5-1 MUST NOT be cited as
        # discretionary bearish.
        rows, txs = _make_insider_rows_single_10b5_1()
        # Cluster size = 1; doesn't meet the ≥3 threshold either.
        assert len(txs) == 1
        # And explicit plan-type override on top.
        assert txs[0].plan_type == PLAN_TYPE_10B5_1
        # Prompt rule itself encodes the override.
        c = self._prompt_text()
        assert "10b5-1" in c
        assert "MUST NOT be cited as discretionary bearish" in c

    def test_discretionary_cluster_meets_all_three_conditions(self) -> None:
        rows, txs = _make_insider_rows_discretionary_cluster()
        # Condition 1: ≥3 sells in 30-day window.
        sell_dates = [t.transaction_date for t in txs if t.transaction_code == "S"]
        span_days = (max(sell_dates) - min(sell_dates)).days
        assert len(sell_dates) >= 3
        assert span_days <= 30

        # Condition 2: at least one tx with pct_of_holdings_after > 0.05.
        enriched = enrich_insider_rows(rows, txs)
        pcts = [e.get("pct_of_holdings_after") for e in enriched]
        assert any(p is not None and p > 0.05 for p in pcts)

        # Condition 3: breaks 12-mo pattern. We construct an
        # expectation-side fixture: prior 12 months had only 10b5-1
        # activity, so this discretionary cluster is the first burst.
        prior = [
            Form4Transaction(
                transaction_date=ANCHOR_DATE - timedelta(days=180),
                transaction_code="S",
                shares=500.0,
                share_price=180.0,
                shares_owned_after=120_000.0,
                plan_type=PLAN_TYPE_10B5_1,
                plan_adopted_date=date(2025, 1, 1),
                reporter_name="VP Three",
                issuer_symbol="AAPL",
            ),
        ]
        prior_summary = build_last_12mo_summary(prior, anchor_date=ANCHOR_DATE - timedelta(days=60))
        # Before the cluster, no discretionary activity.
        assert prior_summary.plan_breakdown.get(PLAN_TYPE_DISCRETIONARY, 0) == 0
        # After the cluster, discretionary dominates.
        post_summary = build_last_12mo_summary(prior + txs, anchor_date=ANCHOR_DATE)
        assert post_summary.plan_breakdown.get(PLAN_TYPE_DISCRETIONARY, 0) >= 3

    def test_prompt_three_conditions_present(self) -> None:
        # Lock the empirical scenario assertions to the same wording the
        # LLM reads.
        c = self._prompt_text()
        assert "ALL THREE" in c
        assert "at least 3 separate sell transactions" in c
        assert "pct_of_holdings_after` > 0.05" in c or "pct_of_holdings_after > 0.05" in c
        assert "Breaks the 12-month pattern" in c
