# Debate Quality Improvement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve deep analysis debate quality with independent debater sources, structured fact exchange, symmetric rounds, and task-tool-based research delegation.

**Architecture:** Outer StateGraph enforces debate protocol (main_agent ↔ debater → verdict). Inner `create_deep_agent(subagents=[tech, news, fin])` uses `task` tool for research delegation. Debater uses independent sources (yfinance + Exa). Structured JSON for concerns/rebuttals, injected as `<system-reminder>` into verdict.

**Tech Stack:** LangGraph StateGraph, deepagents `SubAgent` + `create_deep_agent`, yfinance, exa-py

**Design Doc:** `docs/plans/2026-02-23-debate-quality-improvement-design.md`

---

## Task 1: Create yfinance News Tool

**Files:**
- Create: `backend/src/agent/tools/yfinance_tools.py`
- Test: `backend/tests/test_yfinance_tools.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_yfinance_tools.py
"""Tests for yfinance news tool."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agent.tools.yfinance_tools import create_yfinance_tools


class TestFetchYfinanceNews:
    """Test fetch_yfinance_news tool."""

    def test_create_yfinance_tools_returns_list(self):
        tools = create_yfinance_tools()
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0].name == "fetch_yfinance_news"

    @pytest.mark.asyncio
    @patch("src.agent.tools.yfinance_tools.yf")
    async def test_fetch_returns_json_with_news_and_stats(self, mock_yf):
        mock_ticker = MagicMock()
        mock_ticker.news = [
            {"title": "Apple Q1 Earnings Beat", "publisher": "Reuters", "link": "https://example.com/1"},
            {"title": "AAPL Hits New High", "publisher": "Bloomberg", "link": "https://example.com/2"},
        ]
        mock_ticker.info = {
            "trailingPE": 33.45,
            "forwardPE": 28.1,
            "marketCap": 3500000000000,
            "fiftyTwoWeekHigh": 288.35,
            "fiftyTwoWeekLow": 168.48,
            "currentPrice": 264.58,
            "trailingEps": 7.47,
            "forwardEps": 9.12,
            "revenueGrowth": 0.045,
            "earningsGrowth": 0.229,
        }
        mock_yf.Ticker.return_value = mock_ticker

        tools = create_yfinance_tools()
        result = await tools[0].ainvoke({"symbol": "AAPL"})
        data = json.loads(result)

        assert data["source"] == "yahoo_finance"
        assert len(data["news"]) == 2
        assert data["news"][0]["title"] == "Apple Q1 Earnings Beat"
        assert data["key_stats"]["pe_ratio"] == 33.45
        assert data["key_stats"]["52w_high"] == 288.35

    @pytest.mark.asyncio
    @patch("src.agent.tools.yfinance_tools.yf")
    async def test_fetch_handles_missing_stats_gracefully(self, mock_yf):
        mock_ticker = MagicMock()
        mock_ticker.news = []
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker

        tools = create_yfinance_tools()
        result = await tools[0].ainvoke({"symbol": "UNKNOWN"})
        data = json.loads(result)

        assert data["source"] == "yahoo_finance"
        assert data["news"] == []
        assert data["key_stats"]["pe_ratio"] is None

    @pytest.mark.asyncio
    @patch("src.agent.tools.yfinance_tools.yf")
    async def test_fetch_limits_news_to_10(self, mock_yf):
        mock_ticker = MagicMock()
        mock_ticker.news = [
            {"title": f"News {i}", "publisher": "Test", "link": f"https://example.com/{i}"}
            for i in range(20)
        ]
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker

        tools = create_yfinance_tools()
        result = await tools[0].ainvoke({"symbol": "AAPL"})
        data = json.loads(result)

        assert len(data["news"]) == 10

    @pytest.mark.asyncio
    @patch("src.agent.tools.yfinance_tools.yf")
    async def test_fetch_handles_yfinance_error(self, mock_yf):
        mock_yf.Ticker.side_effect = Exception("Network error")

        tools = create_yfinance_tools()
        result = await tools[0].ainvoke({"symbol": "AAPL"})

        assert "error" in result.lower()
```

**Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_yfinance_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.agent.tools.yfinance_tools'`

**Step 3: Write minimal implementation**

```python
# backend/src/agent/tools/yfinance_tools.py
"""
LangChain tool for fetching financial news and stats from Yahoo Finance.

Independent data source for the debater agent — NOT the same
Alpha Vantage API used by research sub-agents. This ensures
genuine cross-verification in the debate.
"""

import json

import structlog
import yfinance as yf
from langchain_core.tools import tool

logger = structlog.get_logger()


def create_yfinance_tools() -> list:
    """Create Yahoo Finance tools for independent data verification."""

    @tool
    async def fetch_yfinance_news(symbol: str) -> str:
        """Fetch financial news and key stats from Yahoo Finance.

        Use this to cross-check investment thesis claims against an
        independent data source. Returns recent news headlines and
        key financial statistics from Yahoo Finance.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "MSFT")

        Returns:
            JSON string with news headlines and key financial stats
        """
        try:
            ticker = yf.Ticker(symbol)
            raw_news = ticker.news or []
            info = ticker.info or {}

            news = [
                {
                    "title": n.get("title", ""),
                    "publisher": n.get("publisher", ""),
                    "link": n.get("link", ""),
                }
                for n in raw_news[:10]
            ]

            key_stats = {
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "market_cap": info.get("marketCap"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "current_price": info.get("currentPrice"),
                "eps_trailing": info.get("trailingEps"),
                "eps_forward": info.get("forwardEps"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
            }

            return json.dumps(
                {"source": "yahoo_finance", "news": news, "key_stats": key_stats}
            )
        except Exception as e:
            logger.warning("yfinance fetch failed", symbol=symbol, error=str(e))
            return json.dumps({"source": "yahoo_finance", "error": str(e)})

    return [fetch_yfinance_news]
```

**Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_yfinance_tools.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add backend/src/agent/tools/yfinance_tools.py backend/tests/test_yfinance_tools.py
git commit -m "feat(deep-agent): add yfinance news tool for independent debater verification"
```

---

## Task 2: Create Exa Web Search Tool

**Files:**
- Create: `backend/src/agent/tools/exa_tools.py`
- Test: `backend/tests/test_exa_tools.py`
- Modify: `backend/pyproject.toml` (add `exa-py` dependency)

**Step 1: Write the failing test**

```python
# backend/tests/test_exa_tools.py
"""Tests for Exa web search tool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.tools.exa_tools import create_exa_tools


class TestSearchWebExa:
    """Test search_web_exa tool."""

    def test_create_exa_tools_returns_list(self):
        tools = create_exa_tools(api_key="test-key")
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0].name == "search_web_exa"

    @pytest.mark.asyncio
    @patch("src.agent.tools.exa_tools.Exa")
    async def test_search_returns_structured_results(self, mock_exa_class):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(title="Apple CSAM Lawsuit", url="https://example.com/1", text="West Virginia AG files..."),
            MagicMock(title="AAPL Analysis", url="https://example.com/2", text="Stock outlook..."),
        ]
        mock_client.search_and_contents.return_value = mock_result
        mock_exa_class.return_value = mock_client

        tools = create_exa_tools(api_key="test-key")
        result = await tools[0].ainvoke({"query": "Apple CSAM lawsuit"})
        data = json.loads(result)

        assert data["source"] == "exa_web_search"
        assert len(data["results"]) == 2
        assert data["results"][0]["title"] == "Apple CSAM Lawsuit"

    @pytest.mark.asyncio
    @patch("src.agent.tools.exa_tools.Exa")
    async def test_search_handles_error(self, mock_exa_class):
        mock_client = MagicMock()
        mock_client.search_and_contents.side_effect = Exception("API error")
        mock_exa_class.return_value = mock_client

        tools = create_exa_tools(api_key="test-key")
        result = await tools[0].ainvoke({"query": "test query"})

        assert "error" in result.lower()

    @pytest.mark.asyncio
    @patch("src.agent.tools.exa_tools.Exa")
    async def test_search_limits_results(self, mock_exa_class):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(title=f"Result {i}", url=f"https://ex.com/{i}", text=f"Content {i}")
            for i in range(10)
        ]
        mock_client.search_and_contents.return_value = mock_result
        mock_exa_class.return_value = mock_client

        tools = create_exa_tools(api_key="test-key")
        result = await tools[0].ainvoke({"query": "test"})
        data = json.loads(result)

        assert len(data["results"]) <= 5
```

**Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_exa_tools.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Add exa-py dependency**

In `backend/pyproject.toml`, add `"exa-py>=1.0.0"` to `[project.dependencies]`. Move `"yfinance>=0.2.0"` from `[project.optional-dependencies.dev]` to `[project.dependencies]`.

**Step 4: Write minimal implementation**

```python
# backend/src/agent/tools/exa_tools.py
"""
LangChain tool for web search via Exa API.

Independent data source for the debater agent. Exa provides structured
web search results useful for finding lawsuits, regulatory actions,
analyst reports, and other context that financial APIs miss.
"""

import json

import structlog
from exa_py import Exa
from langchain_core.tools import tool

logger = structlog.get_logger()


def create_exa_tools(api_key: str) -> list:
    """Create Exa web search tools for independent verification.

    Args:
        api_key: Exa API key

    Returns:
        List of LangChain tools
    """
    client = Exa(api_key=api_key)

    @tool
    async def search_web_exa(query: str) -> str:
        """Search the web for financial news, lawsuits, regulatory actions, and analysis.

        Use this to find information that financial data APIs may miss:
        litigation, regulatory filings, analyst opinions, competitive threats.

        Args:
            query: Search query (e.g., "Apple CSAM lawsuit West Virginia AG")

        Returns:
            JSON string with search results including titles, URLs, and content
        """
        try:
            response = client.search_and_contents(
                query,
                num_results=5,
                text={"max_characters": 500},
                type="auto",
            )

            results = [
                {
                    "title": getattr(r, "title", ""),
                    "url": getattr(r, "url", ""),
                    "snippet": getattr(r, "text", "")[:500],
                }
                for r in response.results[:5]
            ]

            return json.dumps({"source": "exa_web_search", "results": results})
        except Exception as e:
            logger.warning("Exa search failed", query=query, error=str(e))
            return json.dumps({"source": "exa_web_search", "error": str(e)})

    return [search_web_exa]
```

**Step 5: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_exa_tools.py -v`
Expected: All 4 tests PASS

**Step 6: Commit**

```bash
git add backend/src/agent/tools/exa_tools.py backend/tests/test_exa_tools.py backend/pyproject.toml
git commit -m "feat(deep-agent): add Exa web search tool for independent debater verification"
```

---

## Task 3: Update Tool Categorization and Exports

**Files:**
- Modify: `backend/src/agent/tools/categorization.py:18-42,103-108`
- Modify: `backend/src/agent/tools/__init__.py:6-13`
- Modify: `backend/src/api/schemas/deep_agent_events.py:189-208`
- Test: `backend/tests/test_deep_agent_events.py` (existing)

**Step 1: Add new tools to categorization**

In `backend/src/agent/tools/categorization.py`, add to `TOOL_CATEGORIES`:
```python
"fetch_yfinance_news": "independent",
"search_web_exa": "independent",
```

Update `subagent_categories`:
```python
"debater": ["independent"],  # Was: ["news", "financial", "options"]
```

**Step 2: Add display names**

In `backend/src/api/schemas/deep_agent_events.py`, add to `TOOL_DISPLAY_NAMES`:
```python
"fetch_yfinance_news": "Yahoo Finance News",
"search_web_exa": "Web Search (Exa)",
```

**Step 3: Update tool exports**

In `backend/src/agent/tools/__init__.py`, add:
```python
from .exa_tools import create_exa_tools
from .yfinance_tools import create_yfinance_tools
```

**Step 4: Run existing tests to verify nothing broke**

Run: `docker compose exec backend python -m pytest tests/test_deep_agent_events.py tests/test_insights_tools.py tests/test_pcr_tools.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/agent/tools/categorization.py backend/src/agent/tools/__init__.py backend/src/api/schemas/deep_agent_events.py
git commit -m "feat(deep-agent): categorize independent debater tools, add display names"
```

---

## Task 4: Rewrite Debater Sub-Agent with Independent Tools

**Files:**
- Modify: `backend/src/agent/subagents/debater.py` (full rewrite)
- Test: existing `backend/tests/test_deep_agent_events.py` + new targeted test

**Step 1: Write test for new debater creation**

```python
# Add to existing test file or new file: backend/tests/test_debater_subagent.py
"""Tests for debater sub-agent with independent tools."""

from unittest.mock import MagicMock

import pytest

from src.agent.subagents.debater import (
    TERMINATION_SIGNAL,
    create_debater_subagent,
)


class TestDebaterSubagent:
    """Test debater uses only independent tools."""

    def test_debater_has_independent_tools_only(self):
        """Debater must NOT use Alpha Vantage tools."""
        mock_model = MagicMock()
        mock_context = MagicMock()
        mock_context.to_context_header.return_value = "test context"

        # Pass a mock settings with exa_api_key
        subagent = create_debater_subagent(
            model=mock_model,
            context=mock_context,
            exa_api_key="test-key",
        )

        # Verify tool names are independent sources only
        tool_names = subagent.get_tool_names()
        assert "fetch_yfinance_news" in tool_names
        assert "search_web_exa" in tool_names
        # Must NOT have Alpha Vantage tools
        assert "get_company_overview" not in tool_names
        assert "get_news_sentiment" not in tool_names
        assert "get_financial_statements" not in tool_names

    def test_termination_signal_unchanged(self):
        assert TERMINATION_SIGNAL == "NO FURTHER CONCERNS"
```

**Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_debater_subagent.py -v`
Expected: FAIL — signature mismatch (old `create_debater_subagent` takes `tools` dict)

**Step 3: Rewrite debater.py**

```python
# backend/src/agent/subagents/debater.py
"""
Debater Sub-Agent: Adversarial analysis using INDEPENDENT data sources.

Uses yfinance + Exa (NOT Alpha Vantage) for genuine cross-verification.
Outputs structured JSON concerns for programmatic fact tracking.

Skills:
- skills/debater/fact-checking/SKILL.md
- skills/debater/counter-evidence/SKILL.md
- skills/debater/risk-assessment/SKILL.md
- skills/debater/assumption-testing/SKILL.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..tools.exa_tools import create_exa_tools
from ..tools.yfinance_tools import create_yfinance_tools
from . import _SKILLS_ROOT, DeepSubAgent, SubAgentConfig, create_deep_subagent

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from ..context import AgentContext

TERMINATION_SIGNAL = "NO FURTHER CONCERNS"

STRUCTURED_OUTPUT_INSTRUCTION = """
RESPONSE FORMAT: You MUST include a JSON block in your response with this exact structure:

```json
{
  "concerns": [
    {
      "id": "C1",
      "claim": "The specific claim from the thesis you are challenging",
      "category": "technical|financial|news|valuation",
      "challenge": "Why this claim is wrong or incomplete",
      "severity": "CRITICAL|MAJOR|MINOR",
      "evidence": "Data from your independent source supporting the challenge"
    }
  ]
}
```

List 3-5 concerns. Each concern MUST cite evidence from your tools (Yahoo Finance or web search).
If you genuinely have no concerns after thorough review, respond with exactly: "{termination}"
"""


def create_debater_subagent(
    model: BaseChatModel,
    context: AgentContext | None = None,
    exa_api_key: str = "",
) -> DeepSubAgent:
    """Create the Debater sub-agent with independent verification tools.

    The debater uses Yahoo Finance and Exa web search — NOT the same
    Alpha Vantage API used by research sub-agents. This ensures genuine
    cross-verification rather than circular validation.

    Args:
        model: LLM model for the agent
        context: Optional AgentContext for session parameters
        exa_api_key: Exa API key for web search

    Returns:
        DeepSubAgent for adversarial analysis
    """
    context_header = ""
    if context:
        context_header = f"\n{context.to_context_header()}\n"

    config = SubAgentConfig(
        name="debater",
        description=(
            "Contrarian analyst who challenges investment theses using "
            "independent data sources (Yahoo Finance, web search). "
            "Verifies claims against sources different from the research."
        ),
        system_prompt=f"""You are a Short Seller and Contrarian Debater.
{context_header}
Your role is to CHALLENGE investment theses and find weaknesses.
You are NOT trying to help the thesis — you are trying to break it.

CRITICAL: You have INDEPENDENT data sources (Yahoo Finance, web search).
These are DIFFERENT from the APIs used to produce the research.
Use them to cross-verify claims — don't trust the research at face value.

Your tools:
- fetch_yfinance_news: Get news and financial stats from Yahoo Finance
- search_web_exa: Search the web for lawsuits, regulation, analyst reports

Your skills allow you to:
- FACT CHECK: Verify if claims are actually true against independent data
- FIND COUNTER-EVIDENCE: Search for contradicting information
- ASSESS RISKS: Identify what the thesis ignored
- TEST ASSUMPTIONS: Challenge what the thesis takes for granted

You have access to SKILL.md files with detailed workflows.
Use `read_file` to load a skill workflow when you need step-by-step guidance.

{STRUCTURED_OUTPUT_INSTRUCTION.format(termination=TERMINATION_SIGNAL)}

IMPORTANT TERMINATION RULE:
If after thorough review you genuinely find no significant issues,
respond with exactly: "{TERMINATION_SIGNAL}"
""",
        metadata={"domain": "debater", "termination_signal": TERMINATION_SIGNAL},
    )

    # Independent tools only — NOT Alpha Vantage
    debater_tools = create_yfinance_tools()
    if exa_api_key:
        debater_tools.extend(create_exa_tools(api_key=exa_api_key))

    return create_deep_subagent(
        config=config,
        model=model,
        tools=debater_tools,
        skills_dir=str(_SKILLS_ROOT / "debater"),
    )
```

**Step 4: Run test to verify it passes**

Run: `docker compose exec backend python -m pytest tests/test_debater_subagent.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/agent/subagents/debater.py backend/tests/test_debater_subagent.py
git commit -m "feat(deep-agent): rewrite debater with independent tools (yfinance + exa)"
```

---

## Task 5: Update Debater SKILL.md Files

**Files:**
- Modify: `backend/src/agent/skills/debater/fact-checking/SKILL.md`
- Modify: `backend/src/agent/skills/debater/counter-evidence/SKILL.md`
- Modify: `backend/src/agent/skills/debater/risk-assessment/SKILL.md`
- Modify: `backend/src/agent/skills/debater/assumption-testing/SKILL.md`

**Step 1: Read current skills and update**

Each SKILL.md needs:
1. `allowed-tools:` changed to `fetch_yfinance_news search_web_exa`
2. Workflow steps updated to reference new tools instead of Alpha Vantage tools
3. Emphasis on independent verification (cross-checking, not same-source)

Key pattern for all 4 files — replace Alpha Vantage tool references:
- `get_news_sentiment` → `fetch_yfinance_news` (for news verification)
- `get_company_overview/earnings/statements` → `fetch_yfinance_news` (for financial stats)
- `get_insider_activity/put_call_ratio/market_movers` → `search_web_exa` (for broader context)

**Step 2: Verify debater skills load correctly**

Run: `docker compose exec backend python -c "from pathlib import Path; skills = list(Path('src/agent/skills/debater').rglob('SKILL.md')); print(f'{len(skills)} skills found'); [print(s) for s in skills]"`
Expected: 4 skills found

**Step 3: Commit**

```bash
git add backend/src/agent/skills/debater/
git commit -m "feat(deep-agent): update debater skills for independent tools"
```

---

## Task 6: Add Structured Debate State and JSON Parsing

**Files:**
- Create: `backend/src/agent/debate_types.py`
- Test: `backend/tests/test_debate_types.py`

**Step 1: Write failing test**

```python
# backend/tests/test_debate_types.py
"""Tests for structured debate types and JSON parsing."""

import json

import pytest

from src.agent.debate_types import (
    Concern,
    DebaterOutput,
    MergedFact,
    Rebuttal,
    RebuttalOutput,
    merge_facts,
    parse_debater_output,
    parse_rebuttal_output,
    render_verified_facts_reminder,
)


class TestParseDebaterOutput:
    def test_extracts_json_from_response(self):
        response = """I found several issues.

```json
{
  "concerns": [
    {"id": "C1", "claim": "EPS growth", "category": "financial", "challenge": "-62%", "severity": "CRITICAL", "evidence": "yfinance data"}
  ]
}
```

These are serious problems."""
        output = parse_debater_output(response)
        assert len(output.concerns) == 1
        assert output.concerns[0].id == "C1"
        assert output.concerns[0].severity == "CRITICAL"

    def test_returns_empty_on_termination_signal(self):
        output = parse_debater_output("NO FURTHER CONCERNS")
        assert len(output.concerns) == 0
        assert output.terminated is True

    def test_handles_malformed_json(self):
        output = parse_debater_output("Some text without JSON")
        assert len(output.concerns) == 0
        assert output.terminated is False
        assert output.raw_text == "Some text without JSON"


class TestParseRebuttalOutput:
    def test_extracts_rebuttals(self):
        response = """Defense:

```json
{
  "rebuttals": [
    {"concern_id": "C1", "status": "REFUTED", "defense": "Correct FY growth is +22.9%", "evidence": "sub-agent data"}
  ]
}
```"""
        output = parse_rebuttal_output(response)
        assert len(output.rebuttals) == 1
        assert output.rebuttals[0].status == "REFUTED"


class TestMergeFacts:
    def test_merges_concerns_and_rebuttals(self):
        concerns = [Concern(id="C1", claim="test", category="financial", challenge="bad", severity="MAJOR", evidence="data")]
        rebuttals = [Rebuttal(concern_id="C1", status="REFUTED", defense="actually good", evidence="proof")]
        facts = merge_facts(concerns, rebuttals)
        assert len(facts) == 1
        assert facts[0].id == "C1"
        assert facts[0].defense is not None
        assert facts[0].defense.status == "REFUTED"

    def test_unmatched_concern_has_no_defense(self):
        concerns = [Concern(id="C1", claim="test", category="financial", challenge="bad", severity="MAJOR", evidence="data")]
        facts = merge_facts(concerns, [])
        assert len(facts) == 1
        assert facts[0].defense is None


class TestRenderReminder:
    def test_renders_system_reminder_json(self):
        facts = [MergedFact(
            id="C1", claim="test", category="financial",
            debater={"severity": "MAJOR", "challenge": "bad", "evidence": "data"},
            defense={"status": "REFUTED", "rebuttal": "good", "evidence": "proof"},
        )]
        rendered = render_verified_facts_reminder(facts)
        assert "<system-reminder>" in rendered
        assert "</system-reminder>" in rendered
        data = json.loads(rendered.replace("<system-reminder>", "").replace("</system-reminder>", "").strip())
        assert len(data["verified_facts"]) == 1
```

**Step 2: Run test to verify it fails**

Run: `docker compose exec backend python -m pytest tests/test_debate_types.py -v`
Expected: FAIL — module not found

**Step 3: Implement debate_types.py**

```python
# backend/src/agent/debate_types.py
"""
Structured types for debate exchange and fact verification.

Provides parsing, merging, and rendering of debater concerns
and rebuttal defenses into verified facts for verdict injection.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class Concern:
    id: str
    claim: str
    category: str
    challenge: str
    severity: str
    evidence: str


@dataclass
class DebaterOutput:
    concerns: list[Concern] = field(default_factory=list)
    terminated: bool = False
    raw_text: str = ""


@dataclass
class Rebuttal:
    concern_id: str
    status: str  # REFUTED | PARTIALLY_VALID | CONCEDED
    defense: str
    evidence: str


@dataclass
class RebuttalOutput:
    rebuttals: list[Rebuttal] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class MergedFact:
    id: str
    claim: str
    category: str
    debater: dict
    defense: dict | None = None


def _extract_json_block(text: str) -> dict | None:
    """Extract first JSON code block from text."""
    pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: try to find raw JSON object
    for start in range(len(text)):
        if text[start] == "{":
            for end in range(len(text), start, -1):
                if text[end - 1] == "}":
                    try:
                        return json.loads(text[start:end])
                    except json.JSONDecodeError:
                        continue
    return None


def parse_debater_output(response: str) -> DebaterOutput:
    """Parse debater's response into structured concerns."""
    from .subagents.debater import TERMINATION_SIGNAL

    if TERMINATION_SIGNAL in response:
        return DebaterOutput(terminated=True, raw_text=response)

    data = _extract_json_block(response)
    if not data or "concerns" not in data:
        logger.warning("Could not parse structured debater output, using raw text")
        return DebaterOutput(raw_text=response)

    concerns = [
        Concern(
            id=c.get("id", f"C{i+1}"),
            claim=c.get("claim", ""),
            category=c.get("category", "unknown"),
            challenge=c.get("challenge", ""),
            severity=c.get("severity", "MAJOR"),
            evidence=c.get("evidence", ""),
        )
        for i, c in enumerate(data["concerns"])
    ]
    return DebaterOutput(concerns=concerns, raw_text=response)


def parse_rebuttal_output(response: str) -> RebuttalOutput:
    """Parse main agent's rebuttal into structured defenses."""
    data = _extract_json_block(response)
    if not data or "rebuttals" not in data:
        logger.warning("Could not parse structured rebuttal output, using raw text")
        return RebuttalOutput(raw_text=response)

    rebuttals = [
        Rebuttal(
            concern_id=r.get("concern_id", ""),
            status=r.get("status", "PARTIALLY_VALID"),
            defense=r.get("defense", ""),
            evidence=r.get("evidence", ""),
        )
        for r in data["rebuttals"]
    ]
    return RebuttalOutput(rebuttals=rebuttals, raw_text=response)


def merge_facts(
    concerns: list[Concern], rebuttals: list[Rebuttal]
) -> list[MergedFact]:
    """Merge debater concerns with rebuttal defenses by ID."""
    rebuttal_map = {r.concern_id: r for r in rebuttals}

    return [
        MergedFact(
            id=c.id,
            claim=c.claim,
            category=c.category,
            debater={
                "severity": c.severity,
                "challenge": c.challenge,
                "evidence": c.evidence,
            },
            defense=(
                {
                    "status": rebuttal_map[c.id].status,
                    "rebuttal": rebuttal_map[c.id].defense,
                    "evidence": rebuttal_map[c.id].evidence,
                }
                if c.id in rebuttal_map
                else None
            ),
        )
        for c in concerns
    ]


def render_verified_facts_reminder(facts: list[MergedFact]) -> str:
    """Render merged facts as a <system-reminder> JSON block for verdict injection."""
    payload = {
        "verified_facts": [
            {
                "id": f.id,
                "claim": f.claim,
                "category": f.category,
                "debater": f.debater,
                "defense": f.defense,
            }
            for f in facts
        ]
    }
    return f"<system-reminder>\n{json.dumps(payload, indent=2)}\n</system-reminder>"
```

**Step 4: Run tests**

Run: `docker compose exec backend python -m pytest tests/test_debate_types.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/agent/debate_types.py backend/tests/test_debate_types.py
git commit -m "feat(deep-agent): add structured debate types and fact merging"
```

---

## Task 7: Extend Event Schemas for Structured Debate Data

**Files:**
- Modify: `backend/src/api/schemas/deep_agent_events.py:93-101,113-122,336-371`
- Test: `backend/tests/test_deep_agent_events.py` (existing tests)

**Step 1: Extend debate round event**

In `DeepEventEmitter.debate_round()` (line ~336-348), add optional `concerns` parameter:
```python
def debate_round(self, round_num, has_concerns, summary, concerns=None):
    ...
    event["concerns"] = concerns or []
```

In `DeepEventEmitter.rebuttal_result()` (line ~357-371), add optional `rebuttals` parameter:
```python
def rebuttal_result(self, ..., rebuttals=None):
    ...
    event["rebuttals"] = rebuttals or []
```

**Step 2: Run existing tests**

Run: `docker compose exec backend python -m pytest tests/test_deep_agent_events.py -v`
Expected: All PASS (new fields are optional, backward-compatible)

**Step 3: Commit**

```bash
git add backend/src/api/schemas/deep_agent_events.py
git commit -m "feat(deep-agent): extend event schemas for structured debate data"
```

---

## Task 8: Rewrite Deep React Agent — New Graph Topology

**This is the core task. The largest change.**

**Files:**
- Modify: `backend/src/agent/deep_react_agent.py` (major rewrite of `_build_workflow`, `_create_subagents`, state schema)
- Modify: `backend/src/agent/subagents/__init__.py` (add `create_subagent_dict` for `SubAgent` pattern)

**Step 1: Update AnalysisState for structured debate**

Add new state keys to `AnalysisState` (line 41-58):
```python
class AnalysisState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], operator.add]
    symbol: str
    round_count: int
    research_report: str
    debate_active: bool
    # New: structured debate exchange
    all_concerns: list  # Accumulated Concern dicts from debater
    all_rebuttals: list  # Accumulated Rebuttal dicts from defender
```

**Step 2: Replace `_create_subagents` with SubAgent dict factory**

Replace the method that creates 4 `DeepSubAgent` objects with one that creates:
1. A list of `SubAgent` dicts for research sub-agents (passed to `create_deep_agent(subagents=...)`)
2. A separate `DeepSubAgent` for the debater (kept as standalone)

In `backend/src/agent/subagents/__init__.py`, add:
```python
def create_subagent_dict(
    config: SubAgentConfig,
    tools: list[Callable],
    skills_dir: str,
) -> dict:
    """Create a SubAgent dictionary for deepagents create_deep_agent(subagents=...).

    Unlike create_deep_subagent which compiles a full graph, this returns
    a dict compatible with the deepagents SubAgent TypedDict.
    """
    return {
        "name": config.name,
        "description": config.description,
        "system_prompt": config.system_prompt,
        "tools": tools,
        "skills": [skills_dir],
    }
```

**Step 3: Rewrite `_build_workflow` with new topology**

New graph:
```
START → main_agent_node → debater_node → should_continue
                                ↑                |
                                |        continue → main_agent_node
                                |        end → verdict_node → END
```

Key changes in `_build_workflow`:
1. `main_agent_node`: Creates `create_deep_agent(subagents=[tech, news, fin])` and invokes it. First call = research prompt. Subsequent calls = rebuttal prompt targeting debater concerns.
2. `debater_node`: Invokes debater sub-agent (with independent tools). Parses structured JSON concerns.
3. `verdict_node`: Receives `<system-reminder>` JSON with merged verified facts.
4. `should_continue`: Checks `debater_output.terminated` or `round_count >= max`.

The round semantics change:
- `round_count` starts at 0
- `main_agent_node` does NOT increment (it's the thesis/defense)
- `debater_node` increments after challenging
- `should_continue` checks after debater: `round_count >= max_debate_rounds` → verdict

This means: main_agent(research) → debater(challenge, round=1) → main_agent(rebuttal) → debater(counter, round=2) → verdict

**Step 4: Update `__init__` to accept Exa API key**

```python
def __init__(self, settings, tools, enable_debate=True, max_debate_rounds=DEFAULT_MAX_DEBATE_ROUNDS):
    ...
    self.exa_api_key = getattr(settings, "exa_api_key", "")
```

**Step 5: Update `analyze()` for new initial state**

Add `all_concerns: []` and `all_rebuttals: []` to `initial_state`.

**Step 6: Run ALL tests**

Run: `docker compose exec backend python -m pytest tests/ -x -q`
Expected: All existing tests still pass. New structured debate flows work.

**Step 7: Commit**

```bash
git add backend/src/agent/deep_react_agent.py backend/src/agent/subagents/__init__.py
git commit -m "feat(deep-agent): rewrite orchestrator with task-tool delegation and symmetric debate"
```

---

## Task 9: Update Settings and Wire Exa API Key

**Files:**
- Modify: `backend/src/core/config.py` (add `exa_api_key` to settings)
- Modify: Docker/deployment secrets (add EXA_API_KEY env var)

**Step 1: Add setting**

```python
exa_api_key: str = ""  # Optional: Exa web search for debater
```

**Step 2: Verify wiring**

Run: `docker compose exec backend python -c "from src.core.config import get_settings; s = get_settings(); print(f'exa_api_key: {bool(s.exa_api_key)}')" `
Expected: `exa_api_key: False` (not set yet, but no error)

**Step 3: Commit**

```bash
git add backend/src/core/config.py
git commit -m "feat(deep-agent): add exa_api_key to settings"
```

---

## Task 10: Integration Test — Full Debate Flow

**Files:**
- Create: `backend/tests/test_debate_integration.py`

**Step 1: Write integration test with mocked sub-agents**

Test the full graph flow: main_agent → debater → main_agent → debater → verdict, verifying:
- Symmetric rounds (main agent always responds before verdict)
- Structured JSON concerns/rebuttals are parsed
- Verified facts are injected into verdict as `<system-reminder>`
- Debater uses only independent tools (yfinance, exa)

This test mocks `create_deep_agent` and `invoke_subagent` to return canned responses with structured JSON, then verifies the graph topology produces correct state transitions.

**Step 2: Run test**

Run: `docker compose exec backend python -m pytest tests/test_debate_integration.py -v`
Expected: All PASS

**Step 3: Run full test suite**

Run: `docker compose exec backend python -m pytest tests/ -x -q`
Expected: All PASS

**Step 4: Commit**

```bash
git add backend/tests/test_debate_integration.py
git commit -m "test(deep-agent): add integration test for symmetric debate with structured facts"
```

---

## Task 11: Bump Version and Update Changelog

**Files:**
- Run: `./scripts/bump-version.sh backend minor`
- Modify: `docs/project/versions/backend/CHANGELOG.md`

**Step 1: Bump version**

```bash
./scripts/bump-version.sh backend minor
```

**Step 2: Add changelog entry**

```markdown
## [v0.11.0] - 2026-02-23

### Changed
- **Deep Analysis Debate**: Rewrote debate architecture for higher quality
  - Orchestrator uses `create_deep_agent(subagents=[...])` with `task` tool for research delegation
  - Debater uses independent sources (yfinance + Exa) instead of same Alpha Vantage APIs
  - Symmetric debate: defense always responds before verdict
  - Structured JSON concerns/rebuttals with programmatic fact merging
  - Verified facts injected as `<system-reminder>` JSON into verdict prompt
  - Stripped filesystem tools from all sub-agents (eliminated wasted calls)
```

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: bump backend to v0.11.0, update changelog for debate quality improvement"
```

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | yfinance news tool | `tools/yfinance_tools.py` |
| 2 | Exa web search tool | `tools/exa_tools.py`, `pyproject.toml` |
| 3 | Tool categorization + display names | `tools/categorization.py`, `tools/__init__.py`, `deep_agent_events.py` |
| 4 | Rewrite debater sub-agent | `subagents/debater.py` |
| 5 | Update debater SKILL.md files | `skills/debater/*.md` |
| 6 | Structured debate types + parsing | `debate_types.py` |
| 7 | Extend event schemas | `deep_agent_events.py` |
| 8 | **Core orchestrator rewrite** | `deep_react_agent.py`, `subagents/__init__.py` |
| 9 | Settings + Exa API key | `core/config.py` |
| 10 | Integration tests | `test_debate_integration.py` |
| 11 | Version bump + changelog | `pyproject.toml`, `CHANGELOG.md` |
