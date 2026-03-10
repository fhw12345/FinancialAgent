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
{{
  "concerns": [
    {{
      "id": "C1",
      "claim": "The specific claim from the thesis you are challenging",
      "category": "technical|financial|news|valuation",
      "challenge": "Why this claim is wrong or incomplete",
      "severity": "CRITICAL|MAJOR|MINOR",
      "evidence": "Data from your independent source supporting the challenge"
    }}
  ]
}}
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
