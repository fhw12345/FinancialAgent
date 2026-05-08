"""W3.1 Source provenance model.

Why this exists:
  Wave-2 schema (thesis / valuation / scenarios / catalysts / risks) gave
  the LLM a place to write structured analysis, but every number in the
  output is still a bare float — the reader can't tell whether
  ``pe_ratio: 24.5`` came from AlphaVantage, yfinance fallback, a stale
  cache, or the LLM's prior. Wave 3 fixes this by wrapping every numeric
  (and a few string) field returned by tools in a ``Source`` envelope,
  so:

  - the Phase2 prompt can require thesis bullets to cite source IDs
    ("[AV-2026-05-09]") that the consistency_gate / validators can audit,
  - the frontend can render a footnote superscript [1][2] next to each
    number with hover/click to the actual source URL,
  - downstream gates (Wave-1 consistency_gate, Wave-3 staleness check)
    can reject decisions that cite numbers older than N days.

  ``value`` is intentionally polymorphic — quote-tool prices need
  ``float``, fundamentals tables need ``str | float``, news items and
  insider transactions need ``dict``. Pydantic v2 keeps the union loose
  but every field has a string source identifier and an ISO ``asof``
  timestamp, which is what downstream consumers actually care about.

Used by:
  - W3.2 quote tool (Source-wrap last_price / change_pct / volume)
  - W3.3 fundamentals tool (Source-wrap pe_ratio / market_cap / etc.)
  - W3.4 news tool (Source-wrap headline + url)
  - W3.5 insider tool (Source-wrap each transaction)
  - W3.6 Phase2 prompt (thesis bullets cite Source.id)
  - W3.7 frontend ReportRenderer (footnote tooltip pulls Source.url)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


SOURCE_NAME_MAX = 64
SOURCE_URL_MAX = 2048
SOURCE_ID_MAX = 64


class Source(BaseModel):
    """Provenance envelope for a single tool-produced fact.

    Attributes:
        value: The actual data point. Polymorphic on purpose — quote
            prices are floats, news headlines are strings, insider
            transactions are dicts. Downstream code introspects ``value``
            after looking at the producing tool.
        source: Short, stable identifier of the data origin. Examples:
            ``"alphavantage"``, ``"yfinance"``, ``"sec_edgar_form4"``,
            ``"finnhub_news"``. Lower-cased, no spaces — used in the
            footnote label and in the consistency_gate matcher.
        asof: ISO-8601 datetime when the underlying datum was generated
            (NOT when the tool ran). For a yfinance ``info.regularMarket
            Price`` snapshot, this is "now"; for a 10-Q EPS, this is the
            quarter-end. The Wave-1 staleness gate compares against this.
        url: Optional canonical link the reader can open. ``None`` for
            sources that don't have a public URL (e.g., raw yfinance
            ``info`` fields). Frontend renders the footnote as plain
            text when ``url`` is None.
        id: Stable footnote identifier ("AV-PE-AAPL-2026-05-09"). Auto-
            populated by tool wrappers; left optional so callers can
            still construct ``Source`` objects ad hoc in tests.
    """

    value: Any = Field(
        description=(
            "The data point being attributed. Polymorphic — quote prices "
            "are floats, news items are dicts, etc. Tool wrappers stamp "
            "the concrete shape."
        ),
    )
    source: str = Field(
        min_length=1,
        max_length=SOURCE_NAME_MAX,
        description=(
            "Stable identifier of the upstream data origin (lower-snake-case, "
            "e.g. 'alphavantage', 'yfinance', 'sec_edgar_form4'). Used in "
            "the footnote label and matched by the consistency_gate."
        ),
    )
    asof: datetime = Field(
        description=(
            "ISO-8601 timestamp of the underlying datum (not when the "
            "tool ran). Wave-1 staleness gate compares against this."
        ),
    )
    url: str | None = Field(
        default=None,
        max_length=SOURCE_URL_MAX,
        description=(
            "Canonical reader-facing link for the datum. None when the "
            "origin is API-only (e.g. yfinance.info fields)."
        ),
    )
    id: str | None = Field(
        default=None,
        max_length=SOURCE_ID_MAX,
        description=(
            "Stable footnote ID such as 'AV-PE-AAPL-2026-05-09'. Auto-"
            "populated by tool wrappers; optional so tests stay terse."
        ),
    )

    @field_validator("source")
    @classmethod
    def _normalize_source_name(cls, v: str) -> str:
        # Source names are matched as exact strings by the consistency
        # gate, so we strip and lower-case once at construction time
        # rather than relying on every callsite to be careful.
        return v.strip().lower()

    @field_validator("url")
    @classmethod
    def _validate_url_scheme(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(
                f"url must start with http:// or https://, got {v!r}"
            )
        return v

    def short_label(self) -> str:
        """Compact human-readable label for the footnote chip.

        Falls back to ``source`` when ``id`` is unset, so the renderer
        always has something to print.
        """
        return self.id or self.source
