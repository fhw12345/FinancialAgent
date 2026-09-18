"""Add explicit strategy accounting/identity inputs without rewriting legacy evidence records."""

from typing import Any

from ...models.evidence import EvidenceRecord, EvidenceSnapshot, Family
from ..evidence.adapters import day, make, numeric, source, timestamp


def inputs(
    snapshot: EvidenceSnapshot,
    overview: dict[str, Any],
    cash: dict[str, Any],
    balance: dict[str, Any],
    income: dict[str, Any],
) -> list[EvidenceRecord]:
    out = []
    for field, metric in [
        ("QuoteType", "instrument.type"),
        ("Country", "instrument.country"),
        ("Sector", "instrument.sector"),
        ("Industry", "instrument.industry"),
    ]:
        value = overview.get(field)
        out.append(
            make(
                snapshot,
                "overview",
                metric,
                str(value) if value else None,
                "text",
                provider=source(overview),
                period="instant",
                adapter_version="idq-005@1",
            )
        )
    maps: list[tuple[Family, dict[str, Any], dict[str, str]]] = [
        (
            "cash_flow",
            cash,
            {
                "operatingCashflow": "operating_cash_flow",
                "capitalExpenditures": "capital_expenditure",
                "netIncome": "net_income",
            },
        ),
        (
            "balance_sheet",
            balance,
            {
                "totalDebt": "total_debt",
                "cashAndCashEquivalentsAtCarryingValue": "cash",
            },
        ),
        (
            "income_statement",
            income,
            {
                "dilutedEPS": "eps",
                "dilutedAverageShares": "diluted_shares",
                "interestExpense": "interest_expense",
                "totalRevenue": "revenue",
            },
        ),
    ]
    for family, data, mapping in maps:
        provider = source(data)
        for row in (data.get("annualReports") or [])[:3]:
            currency = row.get("reportedCurrency") or data.get("reportedCurrency")
            basis = "reported_currency"
            if (
                not currency
                and provider == "yfinance"
                and source(overview) == "yfinance"
            ):
                currency = overview.get("FinancialCurrency")
                basis = "provider_current_financialCurrency; not historical PIT"
            for field, metric in mapping.items():
                value = numeric(row.get(field))
                if (
                    provider == "yfinance"
                    and value is not None
                    and metric in ("capital_expenditure", "interest_expense")
                ):
                    value = abs(value)
                    adjustment = basis + "; expense_outflow_normalized@1"
                else:
                    adjustment = basis
                unit = (
                    "shares"
                    if metric == "diluted_shares"
                    else (
                        f"{currency}/share"
                        if metric == "eps" and currency
                        else currency or "unknown"
                    )
                )
                out.append(
                    make(
                        snapshot,
                        family,
                        metric,
                        value,
                        unit,
                        provider=provider,
                        currency=currency,
                        period="annual",
                        period_end=day(row.get("fiscalDateEnding")),
                        published_at=timestamp(row.get("published_at")),
                        document_id=row.get("accessionNumber"),
                        adjustment=adjustment,
                        adapter_version="idq-005@1",
                    )
                )
    return out
