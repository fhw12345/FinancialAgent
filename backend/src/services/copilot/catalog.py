"""Account entitlement + Responses capability filtering, not a model-name override."""

import re
from typing import Any

from pydantic import BaseModel, Field

from .protocol import CopilotError


class CopilotModel(BaseModel):
    id: str
    name: str
    max_output_tokens: int = Field(default=16384, ge=16, le=200000)


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
        if not isinstance(model_id, str) or not model_id or len(model_id) > 120:
            continue
        supported_family = bool(re.match(r"^gpt-[56](?:[.-]|$)", model_id))
        if (
            policy.get("state") in ("disabled", "unconfigured")
            or supports.get("tool_calls") is False
        ):
            continue
        eligible = row.get("model_picker_enabled") is True
        if individual and not picker:
            eligible = policy.get("state") == "enabled"
        endpoints = row.get("supported_endpoints")
        # Older catalogs omit supported_endpoints. Limit compatibility fallback
        # to the GPT reasoning families already supported by this adapter.
        response_capable = (
            "/responses" in endpoints
            if isinstance(endpoints, list)
            else supported_family
        )
        if not eligible or not response_capable or not supported_family:
            continue
        limit = _record(capabilities.get("limits")).get("max_output_tokens", 16384)
        if not isinstance(limit, int) or not 16 <= limit <= 200000:
            limit = 16384
        name = row.get("name")
        result[model_id] = CopilotModel(
            id=model_id,
            name=name if isinstance(name, str) else model_id,
            max_output_tokens=limit,
        )
    return sorted(result.values(), key=lambda model: model.id)
