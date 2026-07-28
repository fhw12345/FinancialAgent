"""Stable prompt identities and versions used by durable runs and evaluations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.agent.portfolio_phase2_prompt import render_portfolio_phase2_prompt


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: str
    version: int
    template: str = ""
    tags: tuple[str, ...] = ()
    renderer: Callable[..., str] | None = None

    @property
    def versioned_id(self) -> str:
        return f"{self.prompt_id}@{self.version}"

    def render(self, **context: Any) -> str:
        if self.renderer is not None:
            return self.renderer(**context)
        if not self.template:
            raise ValueError(f"Prompt {self.versioned_id} has no registered template")
        return self.template.format(**context)


ROUTER_TEMPLATE = """Classify this Financial Agent request into exactly one flow.

v2: direct conversational answer; no current market data or tools needed.
v3: tool-using financial analysis, current data, news, fundamentals, or technical analysis.
v4-deep: explicitly requests comprehensive/deep investment research, multi-angle analysis, or adversarial debate.

Selected symbol from UI: {current_symbol}
User message: {message}
"""
SYMBOL_EXTRACTION_TEMPLATE = """Identify possible US stock ticker symbols in this request.

Return a short search query for the company name and at most three ticker
candidates. Return an empty candidate list when uncertain. Do not invent a
default symbol.

User request: {message}
"""
FINANCIAL_SYSTEM_TEMPLATE = """You are a senior financial analyst with 15+ years of Wall Street experience, conversing naturally with retail investors who value clarity and actionable insights.

**CRITICAL - Current Date: {current_date}**
Use this date as reference for all time-based queries (e.g., "past 6 months" = {six_months_ago} to {current_date}).

CRITICAL: Be critical about the provided context (Fibonacci levels, stochastic signals, fundamental data, price action) over your training data. The context contains real-time market analysis.

Tool Selection Strategy - CRITICAL:
**Start Broad -> Go Deep**: Build context before diving into details
- **Phase 1 (Overview)**: search_ticker, get_company_overview, get_market_movers
- **Phase 2 (Sentiment)**: get_news_sentiment
- **Phase 3 (Deep-Dive)**: get_financial_statements (cash_flow/balance_sheet), fibonacci_analysis_tool, stochastic_analysis_tool

**Execution Rules**:
- **Limit**: Call MAXIMUM 3 tools per reasoning iteration
- **Sequential**: Reason about results before calling next tool batch
- **Purpose-Driven**: Only call tools you need - don't call all tools at once
- **Smart Reasoning**: If overview + sentiment give clear answer, STOP there (no need for financials)

Response Style - Adapt to Context:
- Conclusion first
- Cite specific numbers, explain technical terms
- Honest risks
- Target 500-1000 tokens (hard limit: 3000 tokens)

You MUST:
- Base analysis on provided context data
- Explain technical terms when first introduced
- Reference exact price levels from context

You MUST NOT:
- Call all tools at once
- Use jargon without explanation
- Make vague statements without supporting data
- Exceed 3000 tokens
"""
DEEP_REBUTTAL_TEMPLATE = """{research_context}

The debater raised concerns about {symbol}:

{concern_lines}

Your job is to DEFEND the thesis by addressing each concern with evidence:
1. For each concern, use tools to gather SPECIFIC data that confirms or refutes it
2. If the concern is valid, acknowledge it and explain why the thesis still holds
3. If the concern is wrong, provide evidence that disproves it

Return exactly one JSON object with a `rebuttals` array using this structure:
{{
  "rebuttals": [
    {{
     "concern_id": "Copy the exact displayed ID, for example R1-C1",
      "status": "REFUTED|PARTIALLY_VALID|CONCEDED",
      "defense": "Your defense with specific data",
      "evidence": "Source of your evidence"
    }}
  ]
}}

Do not include prose, commentary, or Markdown code fences outside the JSON object.
Return exactly one rebuttal for every concern shown above, preserving each
displayed concern ID exactly. Every rebuttal must cite specific evidence.
Be concise and focus on data."""
DEEP_DEBATER_TEMPLATE = """{research_context}

Review the following investment thesis and challenge it:

{report}

Your job is to:
1. Use your fact-checking skills to verify key claims
2. Search for counter-evidence and contradicting data
3. Identify overlooked risks and stress-test assumptions

Return exactly one JSON object with a `concerns` array using this structure:
{{
  "concerns": [
    {{
      "id": "C1",
      "claim": "Claim being challenged",
      "category": "technical|fundamental|valuation|risk",
      "challenge": "Specific evidence-based challenge",
      "severity": "MAJOR|MINOR",
      "evidence": "Source or data supporting the challenge"
    }}
  ]
}}

Do not include prose, commentary, or Markdown code fences outside the JSON object.
Every concern must cite real evidence. Be aggressive but fair, not speculative.

If after thorough review you genuinely have no concerns, respond with:
"{termination_signal}"
"""
DEEP_VERDICT_TEMPLATE = """You are a Senior Investment Committee Judge delivering a final verdict.

{verified_facts}

{research_context}

## Research Report
{report}

Produce the registered structured verdict:
- report_markdown: a self-contained final Markdown investment report
- action: BUY, HOLD, or SELL
- conviction: HIGH, MEDIUM, or LOW
- risk_level: HIGH, MODERATE, or LOW
- key_insight: the most important takeaway in 1-2 sentences
- concern_assessments: one entry per concern with concern_id, assessment
  (VERIFIED, NEEDS_MORE_EVIDENCE, or CONTRADICTED), reasoning, and evidence

The Markdown report must explain each concern assessment and the final action,
conviction, risk level, and key insight. It must include an explicit Action or
Recommendation field whose value is exactly one BUY, HOLD, or SELL token and
matches `action`; do not negate or qualify that field value.
Be decisive, use evidence from both sides, and do not hedge excessively."""
CONSISTENCY_GATE_TEMPLATE = """You are a research-quality gate. You will receive:

1. A market-research report for a single stock symbol.
2. A list of `degraded` data signals detected upstream.

Your ONLY job: check whether the report's bullish or bearish thesis bullets
cite any degraded fields as evidence. Return passed=true if no thesis bullet
relies on a degraded signal. Return passed=false with violations containing
the exact quote and degraded field.

Do NOT evaluate general analytical quality. If the degraded list is empty,
return passed=true with no violations."""

_PROMPTS = {
    spec.prompt_id: spec
    for spec in (
        PromptSpec("router", 1, ROUTER_TEMPLATE, ("routing", "structured")),
        PromptSpec(
            "symbol-extraction",
            2,
            SYMBOL_EXTRACTION_TEMPLATE,
            ("symbol", "structured"),
        ),
        PromptSpec(
            "financial-system",
            3,
            FINANCIAL_SYSTEM_TEMPLATE,
            ("chat", "react", "tools"),
        ),
        PromptSpec("deep-rebuttal", 2, DEEP_REBUTTAL_TEMPLATE, ("deep", "debate")),
        PromptSpec("deep-debater", 3, DEEP_DEBATER_TEMPLATE, ("deep", "debate")),
        PromptSpec("deep-verdict", 2, DEEP_VERDICT_TEMPLATE, ("deep", "verdict")),
        PromptSpec(
            "consistency-gate",
            2,
            CONSISTENCY_GATE_TEMPLATE,
            ("portfolio", "validation", "structured"),
        ),
        PromptSpec(
            "portfolio-phase2",
            4,
            tags=("portfolio", "decisions", "structured"),
            renderer=render_portfolio_phase2_prompt,
        ),
    )
}


def get_prompt(prompt_id: str) -> PromptSpec:
    try:
        return _PROMPTS[prompt_id]
    except KeyError as exc:
        raise KeyError(f"Unknown prompt id: {prompt_id}") from exc


def render_prompt(prompt_id: str, **context: Any) -> str:
    return get_prompt(prompt_id).render(**context)


def prompt_registry_snapshot() -> dict[str, str]:
    return {
        prompt_id: spec.versioned_id for prompt_id, spec in sorted(_PROMPTS.items())
    }
