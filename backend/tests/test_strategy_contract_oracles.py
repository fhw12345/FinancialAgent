"""ST-01: a registered fundamental contract must not inherit a short-term execution mandate."""

from src.agent.prompt_registry import get_prompt


def test_fundamental_prompt_is_separate_from_legacy_trade_geometry():
    prompt = get_prompt("strategy-fundamental")
    assert prompt.versioned_id == "strategy-fundamental@1"
    assert "252" in prompt.template and "SPY" in prompt.template
    assert "REQUIRED for BUY/SELL" not in prompt.template
    assert "execution" in prompt.template
