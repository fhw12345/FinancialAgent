import pytest

from src.agent.copilot_chat_model import CopilotChatModel
from src.agent.llm_factory import get_llm, get_role_models, resolve_route
from src.core.config import Settings
from tests.copilot_fixtures import ready_service, sse, text_output


@pytest.mark.asyncio
async def test_native_factory_uses_same_selected_model_for_all_roles(
    tmp_path, monkeypatch
):
    ready_service(tmp_path, lambda _: sse(text_output("ok")), monkeypatch)
    settings = Settings(
        _env_file=None, llm_provider="github_copilot", copilot_state_dir=str(tmp_path)
    )
    monkeypatch.setattr("src.agent.llm_factory.get_settings", lambda: settings)
    assert set(get_role_models(settings).values()) == {"gpt-6-astra"}
    route = resolve_route("react_agent", settings)
    assert route.api_key == ""
    assert route.base_url == "https://api.individual.githubcopilot.com"
    model = get_llm("react_agent", max_tokens=80, streaming=True)
    assert isinstance(model, CopilotChatModel)
    assert (await model.ainvoke("hi")).content == "ok"
