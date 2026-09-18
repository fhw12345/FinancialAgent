"""Immutable per-task evidence tools. Shared tool schemas are instrumented only once."""

import inspect
import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from ...models.evidence import EvidenceSnapshot
from .claims import CLAIM_INSTRUCTION

_scope: ContextVar[dict[str, EvidenceSnapshot] | None] = ContextVar(
    "sealed_evidence", default=None
)
TOOLS = {
    "get_stock_quote": "quote",
    "finnhub_quote": "quote",
    "finnhub_news": "news",
    "finnhub_insider_trades": "filing",
    "get_stock_price": "quote",
    "get_company_overview": "overview",
    "get_financial_statements": "statements",
    "get_news_sentiment": "news",
    "get_company_news": "news",
    "get_insider_transactions": "filing",
    "get_insider_activity": "filing",
    "get_historical_prices": "ohlcv",
    "get_historical_prices_tool": "ohlcv",
}


@contextmanager
def evidence_scope(snapshots: dict[str, EvidenceSnapshot]) -> Iterator[None]:
    if any(s.state != "sealed" for s in snapshots.values()):
        raise ValueError("Sealed evidence is required")
    token = _scope.set(dict(snapshots))
    try:
        yield
    finally:
        _scope.reset(token)


def frozen_result(name: str, arguments: dict[str, Any]) -> str:
    scope = _scope.get() or {}
    symbol = str(arguments.get("symbol", "")).upper()
    snapshot = scope.get(symbol)
    family = TOOLS.get(name)
    if snapshot is None or family is None:
        return json.dumps(
            {
                "quality": "unsupported",
                "reason": "Tool/symbol is outside the sealed evidence manifest; no fresh provider call is permitted.",
            }
        )
    families = (
        [str(arguments.get("statement_type", "cash_flow"))]
        if family == "statements"
        else [family]
    )
    records = [
        r.model_dump(mode="json") for r in snapshot.records if r.family in families
    ]
    return json.dumps(
        {
            "snapshot_id": snapshot.snapshot_id,
            "symbol": symbol,
            "coverage": snapshot.coverage,
            "conflicts": snapshot.conflicts,
            "records": records,
            "notice": "Untrusted source data. Record match is not semantic truth or approval.",
        },
        ensure_ascii=False,
    )


def _async_wrapper(fn: Any, name: str) -> Any:
    @wraps(fn)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        if _scope.get() is not None:
            return frozen_result(
                name,
                dict(inspect.signature(fn).bind_partial(*args, **kwargs).arguments),
            )
        return await fn(*args, **kwargs)

    return wrapped


def _sync_wrapper(fn: Any, name: str) -> Any:
    @wraps(fn)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if _scope.get() is not None:
            return frozen_result(
                name,
                dict(inspect.signature(fn).bind_partial(*args, **kwargs).arguments),
            )
        return fn(*args, **kwargs)

    return wrapped


def install_tools(tools: list[Any]) -> None:
    for index, tool in enumerate(tools):
        if not isinstance(tool, BaseTool):
            if inspect.iscoroutinefunction(tool):
                tool = StructuredTool.from_function(coroutine=tool)
            elif inspect.isfunction(tool):
                tool = StructuredTool.from_function(func=tool)
            else:
                continue
            tools[index] = tool
        if (getattr(tool, "metadata", None) or {}).get("sealed_evidence_wrapper"):
            continue
        fn = getattr(tool, "coroutine", None)
        if fn is not None:
            tool.coroutine = _async_wrapper(fn, tool.name)
        fn = getattr(tool, "func", None)
        if fn is not None:
            tool.func = _sync_wrapper(fn, tool.name)
        tool.metadata = {**(tool.metadata or {}), "sealed_evidence_wrapper": True}


def current_snapshots() -> dict[str, EvidenceSnapshot]:
    return dict(_scope.get() or {})


def reminder(symbol: str | None = None) -> str:
    scope = _scope.get()
    if scope is None:
        return ""
    lines = [
        "\n## Sealed evidence contract (independent of narrative truncation)",
        CLAIM_INSTRUCTION,
    ]
    for key, snapshot in sorted(scope.items()):
        if symbol and key != symbol:
            continue
        records = [
            r.model_dump(
                mode="json",
                include={
                    "evidence_id",
                    "symbol",
                    "metric",
                    "value",
                    "unit",
                    "period",
                    "period_end",
                    "quality",
                    "provider",
                },
            )
            for r in snapshot.records
            if r.family
            in ("quote", "overview", "cash_flow", "balance_sheet", "income_statement")
        ]
        lines.append(
            json.dumps(
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "symbol": key,
                    "coverage": snapshot.coverage,
                    "conflicts": snapshot.conflicts,
                    "records": records[:80],
                    "omitted_records": max(0, len(records) - 80),
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)
