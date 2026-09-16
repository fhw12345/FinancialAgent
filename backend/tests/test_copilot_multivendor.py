import pytest

from src.services.copilot.catalog import parse_catalog


def model(model_id, vendor, endpoints):
    return {
        "id": model_id,
        "name": model_id,
        "vendor": vendor,
        "model_picker_enabled": True,
        "policy": {"state": "enabled"},
        "supported_endpoints": endpoints,
        "capabilities": {"supports": {"tool_calls": True}},
    }


def test_catalog_all_three_vendors_but_not_mai_or_hidden():
    rows = [
        model("gpt-6-astra", "OpenAI", ["/responses"]),
        model("gemini-3.8-flash", "Google", ["/chat/completions"]),
        model("grok-4.6", "xAI", ["/responses"]),
        model("mai-code-1.1-flash", "Microsoft", ["/responses"]),
    ]
    rows.append(
        {
            **model("gemini-hidden", "Google", ["/chat/completions"]),
            "model_picker_enabled": False,
        }
    )
    actual = parse_catalog({"data": rows}, individual=True)
    assert {m.id: m.api for m in actual} == {
        "gpt-6-astra": "openai-responses",
        "gemini-3.8-flash": "openai-completions",
        "grok-4.6": "openai-responses",
    }
