"""Focused tests for Deep structured verdict generation and persistence."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from src.agent.debate_types import (
    DeepVerdict,
    VerdictAssessmentValidationError,
)
from src.agent.deep_react_agent import DeepReActAgent
from src.agent.deep_research_context import DeepResearchContext


def make_agent(verdict_result: object) -> tuple[DeepReActAgent, SimpleNamespace]:
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

    async def invoke(subagent, prompt, **kwargs):
        if subagent.config.name == "debater":
            return "NO FURTHER CONCERNS", 0
        return f"{subagent.config.name} report", 0

    agent._invoke_with_events = AsyncMock(side_effect=invoke)
    structured = SimpleNamespace(ainvoke=AsyncMock(return_value=verdict_result))
    agent.verdict_llm = SimpleNamespace(
        with_structured_output=Mock(return_value=structured)
    )
    return agent, structured


@pytest.mark.asyncio
async def test_structured_verdict_uses_report_markdown_and_emits_prompt_versions():
    verdict = DeepVerdict(
        report_markdown="# Final Report\n\n**Action**: BUY\n\nStructured user answer.",
        action="BUY",
        conviction="HIGH",
        risk_level="MODERATE",
        key_insight="Demand growth outweighs valuation risk.",
        concern_assessments=[],
    )
    agent, structured = make_agent(verdict)
    events: list[dict] = []
    result = await agent.analyze(
        symbol="AAPL",
        user_message="Deeply analyze AAPL.",
        research_context=DeepResearchContext.from_history(
            current_request="Deeply analyze AAPL.",
            conversation_history=[],
        ),
        on_event=events.append,
    )

    agent.verdict_llm.with_structured_output.assert_called_once_with(DeepVerdict)
    assert structured.ainvoke.await_count == 1
    assert result["research_report"] == verdict.report_markdown
    assert result["verdict"]["action"] == "BUY"
    assert result["prompt_versions"] == {
        "deep-debater": "deep-debater@3",
        "deep-verdict": "deep-verdict@2",
    }
    prompt_events = {
        event["prompt_id"]: event["version"]
        for event in events
        if event["type"] == "prompt_used"
    }
    assert prompt_events == result["prompt_versions"]


@pytest.mark.asyncio
async def test_invalid_structured_verdict_fails_without_guessed_action():
    agent, _ = make_agent(
        {
            "report_markdown": "# Invalid",
            "action": "MAYBE",
            "conviction": "HIGH",
            "risk_level": "LOW",
            "key_insight": "Invalid action.",
            "concern_assessments": [],
        }
    )
    agent._persist_verdict_decision = AsyncMock()

    with pytest.raises(ValidationError):
        await agent.analyze(
            symbol="AAPL",
            user_message="Deeply analyze AAPL.",
            research_context=DeepResearchContext.from_history(
                current_request="Deeply analyze AAPL.",
                conversation_history=[],
            ),
        )
    agent._persist_verdict_decision.assert_not_awaited()


def test_verdict_rejects_markdown_action_mismatch():
    with pytest.raises(ValidationError, match="must match structured action"):
        DeepVerdict(
            report_markdown="# Final Report\n\n**Action**: SELL",
            action="BUY",
            conviction="HIGH",
            risk_level="MODERATE",
            key_insight="Conflicting action.",
            concern_assessments=[],
        )


@pytest.mark.asyncio
async def test_persistence_uses_structured_action_directly():
    order_repo = SimpleNamespace(
        upsert=AsyncMock(side_effect=lambda order: order),
    )
    data_manager = SimpleNamespace(
        get_quote=AsyncMock(return_value=SimpleNamespace(price=123.45))
    )
    agent = DeepReActAgent.__new__(DeepReActAgent)
    agent._order_repo = order_repo
    agent._data_manager = data_manager

    await agent._persist_verdict_decision(
        symbol="AAPL",
        action="SELL",
        chat_id="chat-1",
        run_id="run-1",
        message_id="msg-run-1",
    )

    persisted = order_repo.upsert.await_args.args[0]
    assert persisted.side == "sell"
    assert persisted.decision_price == 123.45
    assert persisted.chat_id == "chat-1"
    assert persisted.message_id == "msg-run-1"
    assert persisted.analysis_id == "deep_react_AAPL_run-1"
    assert persisted.metadata == {
        "source": "deep_react_verdict",
        "run_id": "run-1",
    }


@pytest.mark.asyncio
async def test_persistence_rejects_unvalidated_action():
    agent = DeepReActAgent.__new__(DeepReActAgent)
    agent._order_repo = SimpleNamespace(
        upsert=AsyncMock(),
    )
    agent._data_manager = SimpleNamespace()
    with pytest.raises(ValueError):
        await agent._persist_verdict_decision(
            symbol="AAPL",
            action="MAYBE",  # type: ignore[arg-type]
            chat_id="chat-1",
            run_id="run-1",
            message_id="msg-run-1",
        )


@pytest.mark.asyncio
async def test_persistence_is_idempotent_by_analysis_id():
    existing = SimpleNamespace(
        side="buy",
        decision_price=123.45,
    )
    order_repo = SimpleNamespace(
        upsert=AsyncMock(return_value=existing),
    )
    data_manager = SimpleNamespace(
        get_quote=AsyncMock(return_value=SimpleNamespace(price=123.45))
    )
    agent = DeepReActAgent.__new__(DeepReActAgent)
    agent._order_repo = order_repo
    agent._data_manager = data_manager

    await agent._persist_verdict_decision(
        symbol="AAPL",
        action="BUY",
        chat_id="chat-1",
        run_id="run-1",
        message_id="msg-run-1",
    )

    order_repo.upsert.assert_awaited_once()


@pytest.mark.asyncio
async def test_multi_round_concern_ids_remain_unique_and_correctly_assessed():
    verdict = DeepVerdict(
        report_markdown="# Final Report\n\n**Action**: HOLD",
        action="HOLD",
        conviction="MEDIUM",
        risk_level="MODERATE",
        key_insight="The two debate rounds identify distinct risks.",
        concern_assessments=[
            {
                "concern_id": "R1-C1",
                "assessment": "VERIFIED",
                "reasoning": "The first-round concern remains valid.",
                "evidence": "Round one evidence.",
            },
            {
                "concern_id": "R2-C1",
                "assessment": "CONTRADICTED",
                "reasoning": "The second-round concern was refuted.",
                "evidence": "Round two evidence.",
            },
        ],
    )
    agent, structured = make_agent(verdict)
    agent.max_debate_rounds = 2
    debate_round = 0

    async def invoke(subagent, prompt, **kwargs):
        nonlocal debate_round
        if subagent.config.name == "debater":
            debate_round += 1
            return (
                '{"concerns":[{"id":"C1","claim":"Round '
                f'{debate_round} claim","category":"risk","challenge":"Round '
                f'{debate_round} challenge","severity":"MAJOR","evidence":"Round '
                f'{debate_round} evidence"}}]}}',
                0,
            )
        if "The debater raised concerns" in prompt:
            rebuttal_ids = ["R1-C1"]
            if "R2-C1" in prompt:
                rebuttal_ids.append("R2-C1")
            return (
                json.dumps(
                    {
                        "rebuttals": [
                            {
                                "concern_id": concern_id,
                                "status": "REFUTED",
                                "defense": "Defense",
                                "evidence": "Evidence",
                            }
                            for concern_id in rebuttal_ids
                        ]
                    }
                ),
                0,
            )
        return f"{subagent.config.name} report", 0

    agent._invoke_with_events = AsyncMock(side_effect=invoke)
    result = await agent.analyze(
        symbol="AAPL",
        user_message="Deeply analyze AAPL.",
        research_context=DeepResearchContext.from_history(
            current_request="Deeply analyze AAPL.",
            conversation_history=[],
        ),
    )

    assert [concern["id"] for concern in result["all_concerns"]] == [
        "R1-C1",
        "R2-C1",
    ]
    verdict_prompt = structured.ainvoke.await_args.args[0][0].content
    assert '"id": "R1-C1"' in verdict_prompt
    assert '"id": "R2-C1"' in verdict_prompt


@pytest.mark.asyncio
async def test_verdict_rejects_missing_concern_assessment():
    verdict = DeepVerdict(
        report_markdown="# Final Report\n\n**Action**: HOLD",
        action="HOLD",
        conviction="LOW",
        risk_level="HIGH",
        key_insight="A debated concern remains unresolved.",
        concern_assessments=[],
    )
    agent, _ = make_agent(verdict)

    async def invoke(subagent, prompt, **kwargs):
        if subagent.config.name == "debater":
            return (
                '{"concerns":[{"id":"C1","claim":"Risk claim",'
                '"category":"risk","challenge":"Material risk",'
                '"severity":"MAJOR","evidence":"Independent evidence"}]}',
                0,
            )
        if "The debater raised concerns" in prompt:
            return (
                '{"rebuttals":[{"concern_id":"R1-C1",'
                '"status":"CONCEDED","defense":"The risk is valid",'
                '"evidence":"Updated evidence"}]}',
                0,
            )
        return f"{subagent.config.name} report", 0

    agent._invoke_with_events = AsyncMock(side_effect=invoke)
    with pytest.raises(VerdictAssessmentValidationError):
        await agent.analyze(
            symbol="AAPL",
            user_message="Deeply analyze AAPL.",
            research_context=DeepResearchContext.from_history(
                current_request="Deeply analyze AAPL.",
                conversation_history=[],
            ),
        )


@pytest.mark.asyncio
async def test_call_level_debate_override_controls_workflow_topology():
    agent, structured = make_agent(
        DeepVerdict(
            report_markdown="# Final Report\n\n**Action**: HOLD",
            action="HOLD",
            conviction="LOW",
            risk_level="LOW",
            key_insight="Unused when debate is disabled.",
            concern_assessments=[],
        )
    )
    result = await agent.analyze(
        symbol="AAPL",
        enable_debate=False,
        user_message="Analyze AAPL without debate.",
        research_context=DeepResearchContext.from_history(
            current_request="Analyze AAPL without debate.",
            conversation_history=[],
        ),
    )

    structured.ainvoke.assert_not_awaited()
    assert result["round_count"] == 0
    assert "verdict" not in result
