import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.agent.copilot_chat_model import CopilotChatModel
from src.agent.portfolio.agent import PortfolioAnalysisAgent
from src.core.llm_roles import effective_role
from src.services.copilot.catalog import CopilotModel
from src.services.copilot.context import current_profile
from src.services.copilot.protocol import CopilotError
from tests.copilot_fixtures import ready_service, sse, text_output
from tests.copilot_chat_fixtures import chat_sse
from tests.test_copilot_multivendor import model


def setup_roles(tmp_path, handler, monkeypatch):
    service = ready_service(tmp_path, handler, monkeypatch)
    state = service.store.read()
    state.models += [
        CopilotModel(
            id="gemini-3.8-flash",
            name="Gemini",
            api="openai-completions",
            vendor="Google",
        ),
        CopilotModel(id="grok-4.6", name="Grok", vendor="xAI"),
    ]
    state.role_models = {
        "sub_news": "gemini-3.8-flash",
        "sub_debater": "grok-4.6",
        "portfolio_research": "grok-4.6",
    }
    service.store.save(state)
    return service


@pytest.mark.asyncio
async def test_per_role_protocol_and_frozen_routing_snapshot(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        data = json.loads(request.content)
        calls.append((request.url.path, data["model"]))
        if data["model"].startswith("grok"):
            assert "include" not in data
        return (
            chat_sse([{"content": "news"}])
            if request.url.path == "/chat/completions"
            else sse(text_output("result"))
        )

    service = setup_roles(tmp_path, handler, monkeypatch)
    current_profile("simple_chat")
    state = service.store.read()
    state.role_models = {}
    state.routing_revision += 1
    service.store.save(state)
    await CopilotChatModel(role="sub_news").ainvoke("News")
    await CopilotChatModel(role="sub_debater").ainvoke("Review")
    await CopilotChatModel(role="verdict").ainvoke("Decide")
    assert calls == [
        ("/chat/completions", "gemini-3.8-flash"),
        ("/responses", "grok-4.6"),
        ("/responses", "gpt-6-astra"),
    ]


@pytest.mark.asyncio
async def test_whole_map_revision_and_mai_rejection(tmp_path, monkeypatch):
    rows = [
        model("gpt-6-astra", "OpenAI", ["/responses"]),
        model("gemini-3.8-flash", "Google", ["/chat/completions"]),
        model("grok-4.6", "xAI", ["/responses"]),
        model("mai-code-1.1-flash", "Microsoft", ["/responses"]),
    ]
    service = setup_roles(
        tmp_path, lambda _: httpx.Response(200, json={"data": rows}), monkeypatch
    )
    before = service.store.read()
    saved = await service.update_routing(
        {"sub_news": "gemini-3.8-flash"}, before.routing_revision
    )
    assert saved["routing_revision"] == before.routing_revision + 1
    for mapping in [{"bad_role": "gpt-6-astra"}, {"sub_news": "mai-code-1.1-flash"}]:
        with pytest.raises(CopilotError):
            await service.update_routing(mapping, saved["routing_revision"])
    assert service.status()["role_models"] == {"sub_news": "gemini-3.8-flash"}
    with pytest.raises(CopilotError, match="routing_changed"):
        await service.update_routing({}, before.routing_revision)
    service.logout()
    assert service.status()["routing_revision"] > saved["routing_revision"]
    assert service.status()["role_models"] == {}


@pytest.mark.asyncio
async def test_real_portfolio_phases_use_research_and_decision_roles(
    tmp_path, monkeypatch
):
    calls = []

    def handler(request):
        data = json.loads(request.content)
        calls.append(data["model"])
        if data.get("tools"):
            return sse(
                [
                    {
                        "type": "function_call",
                        "call_id": "call_portfolio",
                        "name": data["tools"][0]["name"],
                        "arguments": json.dumps(
                            {
                                "decisions": [],
                                "portfolio_assessment": "Recorded assessment",
                            }
                        ),
                    }
                ]
            )
        return sse(text_output("Recorded research"))

    setup_roles(tmp_path, handler, monkeypatch)

    class React:
        async def ainvoke(self, prompt, **kwargs):
            message = await CopilotChatModel(role="react_agent").ainvoke(prompt)
            return {"final_answer": message.content}

        async def ainvoke_structured(self, *, prompt, schema, **kwargs):
            return (
                await CopilotChatModel(role="react_agent")
                .with_structured_output(schema)
                .ainvoke(prompt)
            )

    agent = object.__new__(PortfolioAnalysisAgent)
    agent.react_agent = React()
    agent.settings = SimpleNamespace(portfolio_analysis_batch_size=5)
    agent._store_portfolio_decision_message = AsyncMock()
    summary = {"holdings_analyzed": 0, "watchlist_analyzed": 0, "errors": []}
    results = await agent._run_phase1_research(
        [], [SimpleNamespace(symbol="EXMP")], "local", False, summary, True
    )
    assert len(results) == 1
    await agent._run_phase2_decisions(
        results,
        {"total_equity": 10000, "cash": 10000, "buying_power": 10000, "positions": []},
        "local",
        False,
    )
    assert calls == ["grok-4.6", "gpt-6-astra"]
    assert effective_role("react_agent") == "react_agent"
    agent._store_portfolio_decision_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_translation_and_consistency_have_independent_actual_roles(
    tmp_path, monkeypatch
):
    from src.core.config import Settings
    from src.services.translation_service import _llm_translate
    from src.agent.portfolio.consistency_gate import run_consistency_gate

    calls = []

    def handler(request):
        data = json.loads(request.content)
        calls.append(data["model"])
        if request.url.path == "/chat/completions":
            return chat_sse([{"content": "译文"}])
        return sse(
            [
                {
                    "type": "function_call",
                    "call_id": "call_gate",
                    "name": "GateVerdict",
                    "arguments": json.dumps(
                        {
                            "passed": False,
                            "violations": [
                                {"field": "Cash flow", "quote": "Cash flow is healthy"}
                            ],
                        }
                    ),
                }
            ]
        )

    service = setup_roles(tmp_path, handler, monkeypatch)
    state = service.store.read()
    state.role_models.update(
        translation="gemini-3.8-flash", consistency_check="grok-4.6"
    )
    service.store.save(state)
    monkeypatch.setattr(
        "src.agent.llm_factory.get_settings",
        lambda: Settings(_env_file=None, llm_provider="github_copilot"),
    )
    assert await _llm_translate(["A sentence"]) == ["译文"]
    verdict, _ = await run_consistency_gate(
        "AAPL", "⚠️ **Cash flow unavailable for AAPL.** Cash flow is healthy"
    )
    assert not verdict.passed
    assert calls == ["gemini-3.8-flash", "grok-4.6"]
