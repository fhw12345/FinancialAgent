"""Account permissions and native API capabilities. MAI is explicitly excluded."""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from .protocol import CopilotError

CopilotAPI = Literal["openai-responses", "openai-completions"]


class CopilotModel(BaseModel):
    id: str
    name: str
    # Defaults keep already-authorized GHC-001 GPT catalogs readable.
    api: CopilotAPI = "openai-responses"
    vendor: str = "OpenAI"
    max_output_tokens: int = Field(default=16384, ge=16, le=200000)
    reasoning_efforts: list[str] = Field(default_factory=list)


def _record(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CopilotError("invalid_model_catalog")
    return value


def parse_catalog(raw: Any, *, individual: bool) -> list[CopilotModel]:
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
        raise CopilotError("invalid_model_catalog")
    rows = [row for row in raw["data"] if isinstance(row, dict)]
    picker = any(
        row.get("model_picker_enabled") is True
        and _record(row.get("policy")).get("state") != "disabled"
        for row in rows
    )
    result = {}
    for row in rows:
        policy = _record(row.get("policy"))
        capabilities = _record(row.get("capabilities"))
        supports = _record(capabilities.get("supports"))
        model_id = row.get("id")
        if not isinstance(model_id, str) or not re.fullmatch(
            r"[a-zA-Z0-9_.-]{1,120}", model_id
        ):
            continue
        vendor = row.get("vendor")
        vendor = vendor if isinstance(vendor, str) else ""
        if model_id.lower().startswith("mai") or vendor.lower() == "microsoft":
            continue
        gpt = bool(re.match(r"^gpt-[56](?:[.-]|$)", model_id))
        gemini = model_id.startswith("gemini-")
        grok = model_id.startswith("grok-")
        if not (gpt or gemini or grok) or capabilities.get("type", "chat") != "chat":
            continue
        if (
            policy.get("state") in ("disabled", "unconfigured")
            or supports.get("tool_calls") is False
        ):
            continue
        eligible = row.get("model_picker_enabled") is True
        if individual and not picker:
            eligible = policy.get("state") == "enabled"
        endpoints = row.get("supported_endpoints")
        if endpoints is None and gpt:  # Compatibility with old GPT catalogs only.
            endpoints = ["/responses"]
        if not eligible or not isinstance(endpoints, list):
            continue
        api: CopilotAPI
        if (gpt or grok) and "/responses" in endpoints:
            api = "openai-responses"
        elif gemini and "/chat/completions" in endpoints:
            api = "openai-completions"
        else:
            continue
        limit = _record(capabilities.get("limits")).get("max_output_tokens", 16384)
        if not isinstance(limit, int) or not 16 <= limit <= 200000:
            limit = 16384
        name = row.get("name")
        efforts = supports.get("reasoning_effort")
        result[model_id] = CopilotModel(
            id=model_id,
            name=name if isinstance(name, str) else model_id,
            api=api,
            vendor=vendor or ("Google" if gemini else "xAI" if grok else "OpenAI"),
            max_output_tokens=limit,
            reasoning_efforts=(
                [e for e in efforts if isinstance(e, str)]
                if isinstance(efforts, list)
                else []
            ),
        )
    return sorted(result.values(), key=lambda model: model.id)
