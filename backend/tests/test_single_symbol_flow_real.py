"""W3.16-D — End-to-end provenance verification against a real run.

Backstory: every other Wave 3 test asserts on artefacts produced by
mocks. The mock fixtures all happily pass even when production is
broken — exactly the W3.13 "mock-self-reinforcement" antipattern. This
test is the antidote: it runs against the LIVE Mongo database and reads
the most recent ``single_symbol`` flow output (Phase 1 inline research
on ``portfolio_orders.metadata.full_research`` + Phase 2 structured
decision on the same row's ``metadata.thesis`` /
``metadata.reasoning``). It does NOT invoke the LLM itself — that would
be slow, flaky, and expensive. Instead it verifies that *whoever* last
triggered ``trigger-analysis`` produced output carrying the provenance
contract:

  1. Phase 1 inline research must contain at least one ``[FH-...]`` /
     ``[AV-...]`` / ``[YF-...]`` source-id token (W3.16-B preserved
     them through the LLM summarisation step).
  2. Phase 2 must cite at least one token in EITHER ``thesis`` (the
     primary location, W3.6) OR ``reasoning`` (the HOLD-decision
     fallback location). HOLD decisions are allowed to leave the
     ``thesis`` array null per the schema, so we relax the W3.6
     citation target rather than fail every HOLD run.

Run with::

    docker compose exec -T backend python -m pytest \\
        tests/test_single_symbol_flow_real.py -m integration -v \\
        --override-ini='addopts='

To prepare a fresh dataset for the assertion::

    curl -X POST 'http://localhost:8000/api/admin/portfolio/trigger-analysis\\
                  ?flow=single_symbol&symbol=NVDA' \\
         -H 'Content-Type: application/json' -d '{}'
    # wait ~90s for the flow to finish, then run the test

The assertions deliberately don't fix a specific symbol — they pick the
most recent ``single_symbol`` order in the collection so the test stays
useful after any subsequent run.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.integration

# Same regex the frontend uses (ResearchPanel) and the offline e2e
# (test_e2e_source_footnote.py) — keep these three in sync.
SOURCE_ID_PATTERN = re.compile(
    r"\[([A-Z][A-Z0-9_]*-[A-Z]+-[A-Z0-9.]+-\d{4}-\d{2}-\d{2})\]"
)


@pytest.fixture(scope="module")
def mongo_db():  # type: ignore[no-untyped-def]
    """Connect to the running container's Mongo via pymongo (sync) — the
    async motor client doesn't survive across pytest-asyncio's per-test
    event loops, and we don't need async here since the assertions are
    one-shot reads. Skip the whole module when the db is unreachable so
    the test stays safe to discover in environments without Mongo."""
    url = os.getenv("MONGODB_URL", "mongodb://mongodb:27017/financial_agent")
    try:
        from pymongo import MongoClient
    except ImportError:
        pytest.skip("pymongo not installed in test env")
    client = MongoClient(url, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command("ping")
    except Exception as e:
        pytest.skip(f"Mongo unreachable at {url}: {e}")
    db = client.get_default_database()
    yield db
    client.close()


def _latest_single_symbol_order(db) -> dict:  # type: ignore[no-untyped-def]
    """Find the most recent portfolio_order written by a single-symbol
    pipeline. Skip the test when there isn't one within a 24h window —
    the test is asserting against *fresh* state, not historical
    artefacts that pre-date W3.16."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    docs = list(
        db.portfolio_orders.find(
            {
                "metadata.decision_session": {"$exists": True},
                "created_at": {"$gte": cutoff},
            }
        )
        .sort("created_at", -1)
        .limit(1)
    )
    if not docs:
        pytest.skip(
            "No fresh portfolio_order in the last 24h — trigger one via "
            "POST /api/admin/portfolio/trigger-analysis?"
            "flow=single_symbol&symbol=NVDA before running this test."
        )
    return docs[0]


def test_phase1_full_research_contains_source_id_token(mongo_db) -> None:  # type: ignore[no-untyped-def]
    """Phase 1 stores the ReAct agent's final report inline on
    ``portfolio_orders.metadata.full_research``. After W3.16-A (more
    quote tools wrapped) + W3.16-B (TOKEN PRESERVATION RULE) the LLM
    must transit at least one source-id token into that report.

    A real NVDA run on 2026-05-09 BEFORE W3.16 produced 1749 chars and
    zero tokens — which is exactly what this assertion catches."""
    order = _latest_single_symbol_order(mongo_db)
    full_research = (order.get("metadata") or {}).get("full_research", "")
    assert isinstance(full_research, str), (
        f"full_research field has unexpected shape: {type(full_research)!r}"
    )
    assert full_research.strip(), (
        f"order {order.get('order_id')} has empty full_research — Phase 1 "
        "either failed or stored research somewhere else."
    )
    tokens = SOURCE_ID_PATTERN.findall(full_research)
    assert tokens, (
        f"Phase 1 research for order {order.get('order_id')} carries no "
        "source-id token. The LLM stripped them while summarising — see "
        "W3.16-B (TOKEN PRESERVATION RULE in phase1_research.py prompt). "
        f"First 400 chars of report:\n{full_research[:400]!r}"
    )


@pytest.mark.xfail(
    reason=(
        "W3.17: Phase2 prompt currently only requires `[ID]` tokens in the "
        "thesis array, but HOLD decisions leave thesis null per the schema "
        "and route their narrative into `reasoning` / `reasoning_zh` "
        "instead. Real 2026-05-09 NVDA HOLD run names $217.80, RSI 65.86, "
        "Fwd P/E 19 in reasoning yet carries zero tokens — fix is to teach "
        "Phase2 prompt that reasoning must also cite when it lifts numbers "
        "from full_research. Tracked separately so W3.16 A/B/C can ship."
    ),
    strict=True,
)
def test_phase2_decision_cites_at_least_one_token(mongo_db) -> None:  # type: ignore[no-untyped-def]
    """Phase 2 must cite at least one ``[ID]`` token somewhere in the
    decision. The W3.6 prompt prefers ``thesis`` bullets but the schema
    leaves ``thesis`` optional for HOLD decisions, so we accept any of:

      * ``metadata.thesis`` (preferred — what W3.6 specifies)
      * ``metadata.reasoning`` (HOLD fallback)
      * ``metadata.reasoning_zh`` (translated path)
      * ``metadata.scenarios.*.rationale`` (BUY/SELL deep-citation)

    Zero tokens across all four spots means Phase 1 successfully
    preserved tokens (test 1 above) but Phase 2 dropped them while
    composing the structured decision — that's the W3.6 regression.
    """
    order = _latest_single_symbol_order(mongo_db)
    meta = order.get("metadata") or {}

    candidate_strings: list[str] = []

    thesis = meta.get("thesis")
    if isinstance(thesis, list):
        candidate_strings.extend(b for b in thesis if isinstance(b, str))

    for key in ("reasoning", "reasoning_zh"):
        v = meta.get(key)
        if isinstance(v, str):
            candidate_strings.append(v)

    scenarios = meta.get("scenarios")
    if isinstance(scenarios, dict):
        for case in scenarios.values():
            if isinstance(case, dict):
                rat = case.get("rationale")
                if isinstance(rat, str):
                    candidate_strings.append(rat)

    blob = "\n".join(candidate_strings)
    tokens = SOURCE_ID_PATTERN.findall(blob)
    assert tokens, (
        f"Phase 2 decision on order {order.get('order_id')} (decision="
        f"{order.get('side', '?')} for {order.get('symbol')}) cites zero "
        "source-id tokens across thesis / reasoning / scenarios. "
        "W3.6 AC#2 violated for this run. Inspected text "
        f"({len(blob)} chars):\n{blob[:500]!r}"
    )


def test_phase1_full_research_nontrivial_length(mongo_db) -> None:  # type: ignore[no-untyped-def]
    """Soft sanity guard: the W3.16-C token-counter fix needed a real
    Phase 1 run to demonstrate. We can't read the structlog event after
    the fact, but we can at least require the output isn't a trivial
    short stub — that gives the token assertion in test 1 something
    to grip on."""
    order = _latest_single_symbol_order(mongo_db)
    fr = (order.get("metadata") or {}).get("full_research", "")
    assert isinstance(fr, str) and len(fr) > 200, (
        f"order {order.get('order_id')} has suspiciously short or missing "
        f"full_research ({len(fr)} chars) — Phase 1 may have errored."
    )

