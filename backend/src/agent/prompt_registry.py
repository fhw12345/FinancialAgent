"""Stable prompt identities and versions used by durable runs and evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: str
    version: int
    template: str = ""
    tags: tuple[str, ...] = ()

    @property
    def versioned_id(self) -> str:
        return f"{self.prompt_id}@{self.version}"

    def render(self, **context: Any) -> str:
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

RESPONSE FORMAT: Include a JSON block with a `rebuttals` array containing
the exact structure:
```json
{{
  "rebuttals": [
    {{
      "concern_id": "C1",
      "status": "REFUTED|PARTIALLY_VALID|CONCEDED",
      "defense": "Your defense with specific data",
      "evidence": "Source of your evidence"
    }}
  ]
}}
```

Be concise — focus on DATA, not rhetoric."""
DEEP_DEBATER_TEMPLATE = """{research_context}

Review the following investment thesis and challenge it:

{report}

Your job is to:
1. Use your fact-checking skills to verify key claims
2. Search for counter-evidence and contradicting data
3. Identify overlooked risks and stress-test assumptions

RESPONSE FORMAT: Include a JSON block with a `concerns` array containing id,
the exact structure:
```json
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
```

Be aggressive but fair. Use real evidence, not speculation.

If after thorough review you genuinely have no concerns, respond with:
"{termination_signal}"
"""
DEEP_VERDICT_TEMPLATE = """You are a Senior Investment Committee Judge delivering a final verdict.

{verified_facts}

{research_context}

## Research Report
{report}

For EACH concern raised by the Debater, categorize it:
- ✅ **VERIFIED**: [concern] — [1-sentence reasoning citing specific data]
- ⚠️ **NEEDS MORE EVIDENCE**: [concern] — [what data is missing]
- ❌ **CONTRADICTED**: [concern] — [evidence that disproves it]

Then provide:

### Final Verdict
- **Action**: Buy / Hold / Sell
- **Conviction**: High / Medium / Low
- **Risk Level**: HIGH / MODERATE / LOW
- **Key Insight**: 1-2 sentences on the most important takeaway

Be decisive. Use evidence from both sides. Do not hedge excessively."""

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
        PromptSpec("deep-rebuttal", 1, DEEP_REBUTTAL_TEMPLATE, ("deep", "debate")),
        PromptSpec("deep-debater", 2, DEEP_DEBATER_TEMPLATE, ("deep", "debate")),
        PromptSpec("deep-verdict", 1, DEEP_VERDICT_TEMPLATE, ("deep", "verdict")),
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
