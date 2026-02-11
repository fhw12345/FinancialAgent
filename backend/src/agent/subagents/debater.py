"""
Debater Sub-Agent: Adversarial analysis and thesis verification specialist.

Uses deepagents with SKILL.md files for progressive disclosure:
- skills/debater/fact-checking/SKILL.md
- skills/debater/counter-evidence/SKILL.md
- skills/debater/risk-assessment/SKILL.md
- skills/debater/assumption-testing/SKILL.md
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..context import AgentContext
from ..tools.categorization import get_tools_for_subagent
from . import DeepSubAgent, SubAgentConfig, _SKILLS_ROOT, create_deep_subagent

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


TERMINATION_SIGNAL = "NO FURTHER CONCERNS"


def create_debater_subagent(
    tools: dict[str, Callable],
    model: "BaseChatModel",
    context: AgentContext | None = None,
) -> DeepSubAgent:
    """
    Create the Debater/Adversarial Analysis sub-agent.

    Args:
        tools: Dictionary of available tools by name (full tool dict)
        model: LLM model for the agent
        context: Optional AgentContext for session parameters

    Returns:
        DeepSubAgent for adversarial analysis
    """
    context_header = ""
    if context:
        context_header = f"\n{context.to_context_header()}\n"

    config = SubAgentConfig(
        name="debater",
        description=(
            "Adversarial analyst who challenges investment theses. Use for "
            "fact-checking, finding counter-evidence, identifying overlooked "
            "risks, and stress-testing assumptions."
        ),
        system_prompt=f"""You are a Short Seller and Contrarian Debater.
{context_header}
Your role is to CHALLENGE investment theses and find weaknesses.
You are NOT trying to help the thesis - you are trying to break it.

RESPONSE FORMAT: Be CONCISE and PRECISE.
- List exactly 3-5 specific concerns as bullet points
- Each concern MUST cite evidence or name the missing data
- Do NOT write lengthy analysis paragraphs
- Each bullet should be 1-2 sentences max

Your skills allow you to:
- FACT CHECK: Verify if claims are actually true
- FIND COUNTER-EVIDENCE: Search for contradicting data
- ASSESS RISKS: Identify what the thesis ignored
- TEST ASSUMPTIONS: Challenge what the thesis takes for granted

You have access to SKILL.md files with detailed workflows.
Use `read_file` to load a skill workflow when you need step-by-step guidance.

IMPORTANT TERMINATION RULE:
If after thorough review you genuinely find no significant issues with the thesis,
respond with exactly: "{TERMINATION_SIGNAL}"
Only say this if you truly have no remaining concerns.
""",
        metadata={"domain": "debater", "termination_signal": TERMINATION_SIGNAL},
    )

    debater_tools = list(get_tools_for_subagent(
        list(tools.values()), "debater"
    ).values())

    return create_deep_subagent(
        config=config,
        model=model,
        tools=debater_tools,
        skills_dir=str(_SKILLS_ROOT / "debater"),
    )
