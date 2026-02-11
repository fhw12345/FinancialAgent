"""
Sub-Agents Module: Specialist agents powered by deepagents library.

Sub-agents are the second layer in the hierarchical agent architecture:
    Main Agent -> Sub-Agents -> Skills (SKILL.md) -> Tools

Each sub-agent:
- Has a specific domain expertise (Technical, News, Financial, Debater)
- Uses SKILL.md files for progressive disclosure via deepagents SkillsMiddleware
- Has access to built-in filesystem tools for reading skill files
- Strategically uses domain-specific tools as directed by skills

Architecture:
    Sub-Agent receives task from Main Agent
    -> deepagents reads SKILL.md frontmatter (name + description)
    -> LLM reads full SKILL.md on demand via read_file
    -> Follows skill workflow instructions
    -> Uses tools as directed by skill
    -> Returns analysis to Main Agent
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = structlog.get_logger()

# Root directory for all skills (parent of technical/, financial/, etc.)
_SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"
# Backend root for FilesystemBackend (the agent/ directory)
_BACKEND_ROOT = str(_SKILLS_ROOT.parent)


@dataclass
class SubAgentConfig:
    """Configuration for a sub-agent."""

    name: str
    description: str
    system_prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)


class DeepSubAgent:
    """
    Sub-agent powered by deepagents library.

    Wraps a create_deep_agent() compiled graph with metadata
    needed by the orchestrator (name, tool names for events).
    """

    def __init__(
        self,
        config: SubAgentConfig,
        graph: "CompiledStateGraph",
        tool_names: list[str],
    ):
        self.config = config
        self.graph = graph
        self.tool_names = tool_names

        logger.info(
            "DeepSubAgent initialized",
            name=config.name,
            custom_tools=len(tool_names),
        )

    def get_tool_names(self) -> list[str]:
        """Get names of custom (non-built-in) tools for event emission."""
        return self.tool_names


def create_deep_subagent(
    config: SubAgentConfig,
    model: Any,
    tools: list[Callable],
    skills_dir: str,
) -> DeepSubAgent:
    """
    Create a DeepSubAgent using deepagents library.

    Args:
        config: SubAgentConfig with name, description, system prompt
        model: LangChain chat model (ChatTongyi)
        tools: List of domain-specific tool functions
        skills_dir: Path to the skills directory for this domain

    Returns:
        DeepSubAgent wrapping a compiled deep agent graph
    """
    tool_names = [getattr(t, "name", str(t)) for t in tools]

    graph = create_deep_agent(
        model=model,
        tools=tools,
        skills=[skills_dir],
        backend=FilesystemBackend(root_dir=_BACKEND_ROOT, virtual_mode=True),
        system_prompt=config.system_prompt,
    )

    return DeepSubAgent(config=config, graph=graph, tool_names=tool_names)


# Re-export for convenience
__all__ = ["DeepSubAgent", "SubAgentConfig", "create_deep_subagent"]
