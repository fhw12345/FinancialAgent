"""Explicit financial-unit/period adapters. Unknown provenance never becomes verified PIT."""

import math
from datetime import UTC, date, datetime
from typing import Any

from ...models.evidence import EvidenceRecord, EvidenceSnapshot, Family
from ...models.portfolio_risk import PortfolioRiskSnapshot
from .identity import identify


def timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )
    if isinstance(value, str):
        try:
            return timestamp(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def source(data: dict[str, Any]) -> str:
    return (
        str(data.get("_source"))
        if data.get("_source") in ("yfinance", "alphavantage", "finnhub", "sec")
        else "unknown"
    )


def make(
    snapshot: EvidenceSnapshot,
    family: Family,
    metric: str,
    value: Any,
    unit: str,
    **extra: Any,
) -> EvidenceRecord:
    value = value if isinstance(value, str) else numeric(value)
    quality = (
        "missing"
        if value is None
        else "unsupported" if unit == "unknown" else "available"
    )
    provider = extra.pop("provider", "unknown")
    exchange = extra.pop("exchange", None)
    currency = extra.pop("currency", None)
    return identify(
        EvidenceRecord(
            snapshot_id=snapshot.snapshot_id,
            symbol=snapshot.symbol,
            instrument_id=f'{snapshot.symbol}@{exchange or "unknown"}:{currency or "unknown"}',
            exchange=exchange,
            currency=currency,
            family=family,
            metric=metric,
            value=value,
            unit=unit,
            quality=quality,
            provider=provider,
            fetched_at=datetime.now(UTC),
            point_in_time_status=(
                "retrieval_only" if provider != "unknown" else "unknown"
            ),
            **extra,
        )
    )


def quote(
    snapshot: EvidenceSnapshot,
    data: Any,
    currency: str | None,
    risk: PortfolioRiskSnapshot | None,
) -> list[EvidenceRecord]:
    result = []
    close_day = risk.session_date if risk else None
    for asset in risk.assets if risk else []:
        if asset.symbol == snapshot.symbol:
            result.append(
                make(
                    snapshot,
                    "quote",
                    "price.close_reference",
                    asset.mark,
                    asset.currency or "unknown",
                    currency=asset.currency,
                    provider=asset.source,
                    period="session",
                    period_end=close_day,
                    session="closed",
                    adjustment="raw_close_reference",
                    document_id=risk.snapshot_id if risk else None,
                )
            )
    if data is not None:
        provider = getattr(data, "source", None) or "unknown"
        quote_day = day(getattr(data, "latest_trading_day", None))
        session = getattr(data, "session", None)
        is_close = session == "closed" and quote_day == close_day
        metric = "price.close_reference" if is_close else "price.last"
        # QuoteData.asof is retrieval metadata, NOT an actual quote observation time.
        result.append(
            make(
                snapshot,
                "quote",
                metric,
                getattr(data, "price", None),
                currency or "unknown",
                currency=currency,
                provider=provider,
                period="session" if is_close else "instant",
                period_end=quote_day,
                observed_at=timestamp(getattr(data, "observed_at", None)),
                session="closed" if is_close else session,
                adjustment="raw_close_reference" if is_close else "last_trade",
                legacy_aliases=[
                    f'{ {"finnhub":"FH","yfinance":"YF","alphavantage":"AV"}.get(provider,"UNKNOWN") }-Q-{snapshot.symbol}-{quote_day}'
                ],
            )
        )
    return result or [make(snapshot, "quote", "price.last", None, "unknown")]


def overview(snapshot: EvidenceSnapshot, data: dict[str, Any]) -> list[EvidenceRecord]:
    provider = source(data)
    currency = data.get("Currency") or None
    financial = data.get("FinancialCurrency") or (
        currency if provider == "alphavantage" else None
    )
    common = {
        "provider": provider,
        "exchange": data.get("Exchange") or None,
        "currency": currency,
        "source_uri": (
            f"https://finance.yahoo.com/quote/{snapshot.symbol}/"
            if provider == "yfinance"
            else None
        ),
    }
    result = []
    mapping = {
        "EPS": ("eps", f"{financial}/share" if financial else "unknown", "ttm"),
        "RevenueTTM": ("revenue", financial or "unknown", "ttm"),
        "PERatio": ("pe", "ratio", "instant"),
        "ProfitMargin": ("net_margin", "ratio", "ttm"),
        "MarketCapitalization": ("market_cap", currency or "unknown", "instant"),
    }
    for key, (metric, unit, period) in mapping.items():
        # LatestQuarter alone cannot prove the start/end of a rolling TTM window.
        result.append(
            make(
                snapshot,
                "overview",
                metric,
                numeric(data.get(key)),
                unit,
                period=period,
                **common,
            )
        )
    return result


STATEMENTS = {
    "cash_flow": {
        "operatingCashflow": "operating_cash_flow",
        "capitalExpenditures": "capital_expenditure",
        "netIncome": "net_income",
    },
    "balance_sheet": {
        "totalAssets": "total_assets",
        "totalLiabilities": "total_liabilities",
        "cashAndCashEquivalentsAtCarryingValue": "cash",
        "commonStockSharesOutstanding": "shares_outstanding",
    },
}


def statements(
    snapshot: EvidenceSnapshot, family: Family, data: dict[str, Any]
) -> list[EvidenceRecord]:
    result = []
    for bucket, period in [
        ("quarterlyReports", "quarter"),
        ("annualReports", "annual"),
    ]:
        for row in (data.get(bucket) or [])[:3]:
            currency = row.get("reportedCurrency") or data.get("reportedCurrency")
            for key, metric in STATEMENTS[family].items():
                value = numeric(row.get(key))
                unit = (
                    "shares"
                    if metric == "shares_outstanding"
                    else currency or "unknown"
                )
                result.append(
                    make(
                        snapshot,
                        family,
                        metric,
                        value,
                        unit,
                        currency=currency,
                        provider=source(data),
                        period=period,
                        period_end=day(row.get("fiscalDateEnding")),
                        published_at=timestamp(row.get("published_at")),
                        document_id=str(row.get("accessionNumber") or "") or None,
                        adjustment="provider_reported",
                    )
                )
    return result or [make(snapshot, family, "statement", None, "unknown")]


def ohlcv(
    snapshot: EvidenceSnapshot, rows: list[Any], currency: str | None
) -> list[EvidenceRecord]:
    result = []
    for row in sorted(rows, key=lambda row: str(getattr(row, "date", "")))[-60:]:
        for field in ("open", "high", "low", "close", "volume"):
            result.append(
                make(
                    snapshot,
                    "ohlcv",
                    "ohlcv." + field,
                    getattr(row, field, None),
                    "shares" if field == "volume" else currency or "unknown",
                    currency=currency,
                    period="session",
                    period_end=day(getattr(row, "date", None)),
                    provider=getattr(row, "source", None) or "data_manager:unreported",
                    adjustment=getattr(row, "adjustment", "unknown"),
                )
            )
    return result or [make(snapshot, "ohlcv", "ohlcv.close", None, "unknown")]


def news(snapshot: EvidenceSnapshot, rows: list[Any]) -> list[EvidenceRecord]:
    result = []
    for row in rows[:5]:
        published = timestamp(getattr(row, "date", None))
        result.append(
            make(
                snapshot,
                "news",
                "headline",
                str(getattr(row, "title", ""))[:1000],
                "text",
                provider="data_manager:unreported",
                period="event",
                period_end=day(published),
                published_at=published,
                document_id=None,
            )
        )
    return result or [
        # Empty legacy lists also represent provider failure; they cannot prove zero news.
        make(snapshot, "news", "headline", None, "text", period="event")
    ]


def filings(
    snapshot: EvidenceSnapshot, rows: list[dict[str, Any]]
) -> list[EvidenceRecord]:
    result = []
    for row in rows[:10]:
        provider = source(row)
        published = timestamp(row.get("accepted_at"))
        result.append(
            make(
                snapshot,
                "filing",
                "insider.shares",
                numeric(row.get("change") or row.get("shares")),
                "shares",
                provider=provider,
                period="event",
                period_end=day(
                    row.get("transactionDate") or row.get("transaction_date")
                ),
                published_at=published,
                document_id=row.get("accession_number"),
                source_uri=row.get("source_url"),
            )
        )
    return result or [
        # No filing receipt is not proof that no filing exists.
        make(snapshot, "filing", "insider.shares", None, "shares", period="event")
    ]
