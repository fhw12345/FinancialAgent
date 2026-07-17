"""Integration test for context injection into real Deep LangGraph prompts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from src.agent.deep_react_agent import DeepReActAgent
from src.agent.deep_research_context import DeepResearchContext


@pytest.mark.asyncio
async def test_specialist_prompts_receive_current_and_prior_context():
    agent = DeepReActAgent.__new__(DeepReActAgent)
    agent.enable_debate = False
    agent.max_debate_rounds = 2
    agent._order_repo = None
    agent._data_manager = None

    subagents = {
        name: SimpleNamespace(
            config=SimpleNamespace(name=name),
            get_tool_names=lambda: [],
        )
        for name in ("technical", "news", "financial", "debater")
    }
    agent._create_subagents = lambda context, cache=None: subagents
    prompts: list[str] = []

    async def invoke(subagent, prompt, **kwargs):
        prompts.append(prompt)
        return f"{subagent.config.name} report", 0

    agent._invoke_with_events = AsyncMock(side_effect=invoke)
    context = DeepResearchContext.from_history(
        current_request="Now focus on downside and challenge the thesis.",
        conversation_history=[
            {
                "role": "user",
                "content": "Analyze SKHY over a 6 month horizon with moderate risk.",
            },
            {
                "role": "assistant",
                "content": "The previous SKHY thesis was bullish.",
            },
        ],
    )

    result = await agent.analyze(
        symbol="SKHY",
        user_message=context.current_request,
        research_context=context,
        enable_debate=False,
    )

    assert len(prompts) == 3
    for prompt in prompts:
        assert "Current request: Now focus on downside" in prompt
        assert "Investment horizon: 6 months" in prompt
        assert "Risk tolerance: moderate" in prompt
        assert "previous SKHY thesis was bullish" in prompt
    assert "technical report" in result["research_report"]


@pytest.mark.asyncio
async def test_debate_prompts_receive_full_prior_context():
    agent = DeepReActAgent.__new__(DeepReActAgent)
    agent.enable_debate = True
    agent.max_debate_rounds = 1
    agent._order_repo = None
    agent._data_manager = None

    subagents = {
        name: SimpleNamespace(
            config=SimpleNamespace(name=name),
            get_tool_names=lambda: [],
        )
        for name in ("technical", "news", "financial", "debater")
    }
    agent._create_subagents = lambda context, cache=None: subagents
    prompts: list[tuple[str, str]] = []

    async def invoke(subagent, prompt, **kwargs):
        prompts.append((subagent.config.name, prompt))
        if subagent.config.name == "debater":
            return (
                """```json
{"concerns":[{"id":"C1","claim":"Valuation is stretched","category":"valuation","challenge":"Test downside","severity":"MAJOR","evidence":"Peer multiples"}]}
```""",
                0,
            )
        if "The debater raised concerns" in prompt:
            return (
                """```json
{"rebuttals":[{"concern_id":"C1","status":"PARTIALLY_VALID","defense":"Growth offsets part of the premium","evidence":"HBM demand"}]}
```""",
                0,
            )
        return f"{subagent.config.name} report", 0

    agent._invoke_with_events = AsyncMock(side_effect=invoke)
    agent.verdict_llm = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=AIMessage(content="### Final Verdict\n- **Action**: Hold")
        )
    )
    context = DeepResearchContext.from_history(
        current_request="Now focus on downside and challenge the thesis.",
        conversation_history=[
            {
                "role": "user",
                "content": "Analyze SKHY over a 6 month horizon with moderate risk.",
            },
            {
                "role": "assistant",
                "content": (
                    "The previous SKHY thesis was bullish. "
                    + ("X" * 700)
                    + " LATEST_RISK_MARKER"
                ),
            },
        ],
    )

    result = await agent.analyze(
        symbol="SKHY",
        user_message=context.current_request,
        research_context=context,
        enable_debate=True,
    )

    specialist_prompts = [
        prompt
        for name, prompt in prompts
        if name in ("technical", "news", "financial")
        and "The debater raised concerns" not in prompt
    ]
    critique_prompt = next(prompt for name, prompt in prompts if name == "debater")
    rebuttal_prompt = next(
        prompt for _, prompt in prompts if "The debater raised concerns" in prompt
    )
    verdict_prompt = agent.verdict_llm.ainvoke.await_args.args[0][0].content

    assert len(specialist_prompts) == 3
    for prompt in specialist_prompts:
        assert "Current request: Now focus on downside" in prompt
        assert "LATEST_RISK_MARKER" not in prompt
    for prompt in (critique_prompt, rebuttal_prompt, verdict_prompt):
        assert "Current request: Now focus on downside" in prompt
        assert "Investment horizon: 6 months" in prompt
        assert "Risk tolerance: moderate" in prompt
        assert "LATEST_RISK_MARKER" in prompt
    assert result["research_report"].startswith("### Final Verdict")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_request", "expected_subagents", "expected_heading"),
    [
        ("Analyze SKHY using technical only.", ["technical"], "Technical Analysis"),
        (
            "Analyze SKHY using valuation only.",
            ["financial"],
            "Fundamental Analysis",
        ),
        (
            "Analyze SKHY but exclude news.",
            ["technical", "financial"],
            "Technical Analysis",
        ),
    ],
)
async def test_exclusive_constraints_filter_specialists(
    user_request: str,
    expected_subagents: list[str],
    expected_heading: str,
):
    agent = DeepReActAgent.__new__(DeepReActAgent)
    agent.enable_debate = False
    agent.max_debate_rounds = 1
    agent._order_repo = None
    agent._data_manager = None

    subagents = {
        name: SimpleNamespace(
            config=SimpleNamespace(name=name),
            get_tool_names=lambda: [],
        )
        for name in ("technical", "news", "financial", "debater")
    }
    agent._create_subagents = lambda context, cache=None: subagents
    invoked: list[str] = []

    async def invoke(subagent, prompt, **kwargs):
        invoked.append(subagent.config.name)
        return f"{subagent.config.name} report", 0

    agent._invoke_with_events = AsyncMock(side_effect=invoke)
    context = DeepResearchContext.from_history(
        current_request=user_request,
        conversation_history=[],
    )

    result = await agent.analyze(
        symbol="SKHY",
        user_message=user_request,
        research_context=context,
        enable_debate=False,
    )

    assert invoked == expected_subagents
    assert expected_heading in result["research_report"]
    assert ("News & Sentiment Analysis" in result["research_report"]) is (
        "news" in expected_subagents
    )
    assert ("Fundamental Analysis" in result["research_report"]) is (
        "financial" in expected_subagents
    )


@pytest.mark.asyncio
async def test_technical_only_debate_stays_with_technical_subagent():
    agent = DeepReActAgent.__new__(DeepReActAgent)
    agent.enable_debate = True
    agent.max_debate_rounds = 1
    agent._order_repo = None
    agent._data_manager = None

    subagents = {
        name: SimpleNamespace(
            config=SimpleNamespace(name=name),
            get_tool_names=lambda: [],
        )
        for name in ("technical", "news", "financial", "debater")
    }
    agent._create_subagents = lambda context, cache=None: subagents
    invoked: list[str] = []

    async def invoke(subagent, prompt, **kwargs):
        invoked.append(subagent.config.name)
        if "Review the following investment thesis" in prompt:
            return (
                """```json
{"concerns":[{"id":"C1","claim":"Momentum is weak","category":"technical","challenge":"Test support","severity":"MAJOR","evidence":"Price action"}]}
```""",
                0,
            )
        if "The debater raised concerns" in prompt:
            return (
                """```json
{"rebuttals":[{"concern_id":"C1","status":"PARTIALLY_VALID","defense":"Support remains intact","evidence":"Price action"}]}
```""",
                0,
            )
        return "technical report", 0

    agent._invoke_with_events = AsyncMock(side_effect=invoke)
    agent.verdict_llm = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=AIMessage(content="### Final Verdict\n- **Action**: Hold")
        )
    )
    request = "Analyze SKHY using technical only and challenge the thesis."
    context = DeepResearchContext.from_history(
        current_request=request,
        conversation_history=[],
    )

    await agent.analyze(
        symbol="SKHY",
        user_message=request,
        research_context=context,
        enable_debate=True,
    )

    assert invoked == ["technical", "technical", "technical"]
