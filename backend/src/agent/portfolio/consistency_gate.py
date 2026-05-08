"""Consistency gate between Phase1 research and Phase2 decisions (W1.10).

Why:
  Phase1's per-symbol research markdown can contain `unsubstantiated`
  banners (data unavailable from both AV and yfinance, see W1.5-W1.8)
  and `STALE FIB SWING` warnings (Fibonacci levels that cannot serve
  as support/resistance, see W1.9). Without an explicit gate, the LLM
  routinely cites those exact fields in its bullish/bearish thesis —
  that's the AAPL "cheapest of seven" incident from 2026-05-07.

How:
  After Phase1 completes, this module runs a single cheap LLM call
  per symbol. The LLM is given (a) the Phase1 markdown and (b) the
  list of degraded fields detected by simple regex on the markdown
  itself. It returns a structured verdict {passed, violations}. On
  fail, the orchestrator can either:
    - retry Phase1 once with the violations injected as a corrective
      hint ("you previously cited X as support but the swing was
      stale; rewrite without it"), or
    - tag the per-symbol result `data_quality=degraded` and let
      Phase2 see the warning explicitly.

  Cost discipline (per PRD D1):
    - cheap model (simple_chat role -> haiku 4.5)
    - max 2k input tokens (truncates research_text to last 6000 chars)
    - one call per symbol (4 holdings = ~$0.04 per run, well under the
      $0.05/run budget the PRD set)
"""

from __future__ import annotations

import re
from typing import Literal

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agent.llm_factory import get_llm

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Detection helpers — pure-function regex (cheap, deterministic)
# ---------------------------------------------------------------------------


_UNAVAILABLE_RX = re.compile(
    r"⚠️\s*\*\*([\w\s]+)\s+unavailable\s+for\s+([A-Z]{1,5})\.\*\*",
    re.IGNORECASE,
)
_STALE_FIB_RX = re.compile(r"STALE\s+FIB\s+SWING")
_RANGE_POS_RX = re.compile(r"range_position:\s*(above_range|below_range|in_range)")


def detect_degraded_fields(research_text: str) -> list[str]:
    """Return human-readable list of degraded data signals in Phase1 output.

    Each element is a one-line string the gate prompt can quote back to
    the LLM, e.g. "Cash flow unavailable for CRWV — do not cite".
    """
    out: list[str] = []
    for match in _UNAVAILABLE_RX.finditer(research_text):
        what, sym = match.group(1).strip(), match.group(2).strip()
        out.append(f"{what} unavailable for {sym} — do not cite as evidence")
    if _STALE_FIB_RX.search(research_text):
        m = _RANGE_POS_RX.search(research_text)
        pos = m.group(1) if m else "out_of_range"
        out.append(
            f"Fibonacci swing is stale (range_position={pos}) — "
            f"do not cite golden zone or any fib level as support/resistance"
        )
    return out


# ---------------------------------------------------------------------------
# LLM verdict schema
# ---------------------------------------------------------------------------


class GateViolation(BaseModel):
    field: str = Field(description="Which degraded field was cited")
    quote: str = Field(
        description="Exact 1-2 line quote from the research that cites it"
    )


class GateVerdict(BaseModel):
    passed: bool
    violations: list[GateViolation] = Field(default_factory=list)
    note: str | None = Field(
        default=None,
        description="One short sentence summarising the verdict; optional",
    )


# ---------------------------------------------------------------------------
# Gate runner
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You are a research-quality gate. You will receive:

1. A market-research report for a single stock symbol.
2. A list of `degraded` data signals detected upstream (data unavailable,
   stale Fibonacci swing, etc.).

Your ONLY job: check whether the report's bullish or bearish thesis
bullets cite any of those degraded fields as evidence. Examples of
violations:
- Report says "P/E unavailable" but thesis says "the stock is the
  cheapest in its cohort".
- Report says "STALE FIB SWING" but thesis says "support at the
  golden zone $264".

Return passed=true if no thesis bullet relies on a degraded signal.
Return passed=false with violations[] listing each. Each violation
includes the exact 1-2 line quote and which degraded field it cites.

Do NOT evaluate the analytical correctness or quality of the report —
only check this single consistency rule. Be terse. If degraded list
is empty, return passed=true with no violations.
"""


_RESEARCH_TRUNCATE_CHARS = 6000


async def run_consistency_gate(
    symbol: str, research_text: str
) -> tuple[GateVerdict, list[str]]:
    """Run the LLM gate against one symbol's Phase1 output.

    Returns (verdict, degraded_fields). `degraded_fields` is the
    deterministic regex list — useful for the caller to log even if
    the LLM call fails. On any LLM error we fail-open (passed=True,
    note set) so a flaky gate cannot wedge the whole pipeline.
    """
    degraded = detect_degraded_fields(research_text)

    if not degraded:
        # Nothing to check; skip the LLM call entirely (cost discipline).
        return GateVerdict(passed=True, note="no degraded fields detected"), []

    truncated = research_text[-_RESEARCH_TRUNCATE_CHARS:]
    user_msg = (
        f"Symbol: {symbol}\n\n"
        f"Degraded signals (from upstream tools):\n"
        + "\n".join(f"- {d}" for d in degraded)
        + f"\n\n--- BEGIN RESEARCH ---\n{truncated}\n--- END RESEARCH ---"
    )

    try:
        llm = get_llm("simple_chat", temperature=0.0, max_tokens=400)
        structured = llm.with_structured_output(GateVerdict)
        verdict = await structured.ainvoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_msg),
            ]
        )
    except Exception as e:  # pragma: no cover — network-class failure
        logger.warning(
            "consistency_gate_llm_failed",
            symbol=symbol,
            error=str(e),
            degraded_count=len(degraded),
        )
        return (
            GateVerdict(
                passed=True,
                note=f"gate failed-open due to LLM error: {e}",
            ),
            degraded,
        )

    logger.info(
        "consistency_gate_verdict",
        symbol=symbol,
        passed=verdict.passed,
        violations=len(verdict.violations),
        degraded_count=len(degraded),
    )
    return verdict, degraded


def violations_as_corrective_hint(
    violations: list[GateViolation],
) -> str:
    """Render a violations list as a corrective hint that can be appended
    to a Phase1 retry prompt."""
    if not violations:
        return ""
    body = "\n".join(
        f"- You wrote: {v.quote!r} — but {v.field}. Rewrite without this claim."
        for v in violations
    )
    return (
        "\n\n## Consistency violations from previous draft (MUST fix)\n\n"
        f"{body}\n\nProduce a new report that does not depend on those "
        "fields. State explicitly that the data is unavailable / the "
        "fib swing is stale where applicable.\n"
    )


# Public re-exports for typing
GateActionLiteral = Literal["accept", "retry", "degrade"]
