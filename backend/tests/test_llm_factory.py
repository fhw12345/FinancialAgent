"""Tests for flag-driven LLM provider routing."""

from unittest.mock import patch

import pytest

from src.agent.llm_factory import (
    get_llm,
    get_role_models,
    resolve_model,
    resolve_route,
)
from src.core.config import Settings
from src.core.exceptions import ConfigurationError


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_maestro_uses_role_specific_model():
    settings = _settings(
        llm_provider="maestro",
        maestro_base_url="http://maestro.test/api/anthropic",
        maestro_auth_token="maestro-token",
        model_react_agent="gpt-test",
    )

    route = resolve_route("react_agent", settings)

    assert route.provider == "maestro"
    assert route.base_url == "http://maestro.test/api/anthropic"
    assert route.api_key == "maestro-token"
    assert route.model == "gpt-test"


def test_direct_anthropic_requires_model_and_key():
    with pytest.raises(ConfigurationError, match="ANTHROPIC_MODEL"):
        resolve_route("simple_chat", _settings(llm_provider="anthropic"))

    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        resolve_route(
            "simple_chat",
            _settings(
                llm_provider="anthropic",
                anthropic_model="claude-direct",
            ),
        )


def test_direct_anthropic_uses_one_configured_model_for_all_roles():
    settings = _settings(
        llm_provider="anthropic",
        anthropic_base_url="https://anthropic.test",
        anthropic_api_key="anthropic-key",
        anthropic_model="claude-direct",
    )

    assert resolve_model("react_agent", settings) == "claude-direct"
    assert resolve_model("sub_debater", settings) == "claude-direct"
    assert resolve_route("summary", settings).base_url == "https://anthropic.test"


def test_copilot_reverse_uses_bridge_defaults_and_optional_override():
    settings = _settings(
        llm_provider="copilot_reverse",
        copilot_reverse_base_url="http://localhost:8765/cc",
    )

    assert resolve_model("react_agent", settings) == "claude-sonnet-5"
    assert resolve_model("simple_chat", settings) == "claude-haiku-4.5"
    assert resolve_model("sub_financial", settings) == "gpt-5.5"
    assert resolve_model("sub_debater", settings) == "gpt-5.5"
    assert resolve_model("summary", settings) == "gpt-5.4-mini"

    overridden = _settings(
        llm_provider="copilot_reverse",
        copilot_reverse_model="claude-sonnet-5",
    )
    assert set(get_role_models(overridden).values()) == {"claude-sonnet-5"}


def test_get_llm_constructs_anthropic_compatible_client():
    settings = _settings(
        llm_provider="copilot_reverse",
        copilot_reverse_base_url="http://localhost:8765/cc/",
        copilot_reverse_auth_token="dummy",
    )

    with (
        patch("src.agent.llm_factory.get_settings", return_value=settings),
        patch("src.agent.llm_factory.ChatAnthropic") as chat_anthropic,
    ):
        get_llm("simple_chat", streaming=True, max_tokens=1234)

    chat_anthropic.assert_called_once_with(
        model_name="claude-haiku-4.5",
        temperature=0.7,
        max_tokens_to_sample=1234,
        streaming=True,
        anthropic_api_url="http://localhost:8765/cc",
        anthropic_api_key="dummy",
    )


def test_latest_maestro_defaults():
    settings = _settings(llm_provider="maestro")

    assert resolve_model("deep_planner", settings) == "claude-opus-4.8"
    assert resolve_model("react_agent", settings) == "claude-sonnet-5"
    assert resolve_model("sub_financial", settings) == "gpt-5.6-sol"
    assert resolve_model("sub_debater", settings) == "gemini-3.1-pro-preview"
    assert resolve_model("summary", settings) == "gemini-3.5-flash"
