from __future__ import annotations

from dataclasses import dataclass

from .live_schemas import CostSource, ModelPricingOverride, ModelUsage

PRICING_CATALOG_VERSION = "2026-08-04"


class MissingModelPricing(ValueError):
    pass


@dataclass(frozen=True)
class ModelPricing:
    input_per_million_usd: float
    output_per_million_usd: float


# Versioned estimates used only when the provider does not return billed cost.
# Overrides are required when a configured model is not listed.
MODEL_PRICING_USD: dict[str, ModelPricing] = {
    "claude-haiku-4.5": ModelPricing(1.0, 5.0),
    "claude-sonnet-5": ModelPricing(3.0, 15.0),
    "claude-opus-4.8": ModelPricing(15.0, 75.0),
    "gpt-5.4-mini": ModelPricing(0.4, 1.6),
    "gpt-5.6-sol": ModelPricing(2.5, 10.0),
    "gemini-3.1-pro-preview": ModelPricing(2.0, 12.0),
    "gemini-3.5-flash": ModelPricing(0.3, 2.5),
    "e2e-model": ModelPricing(0.01, 0.01),
}


def resolve_pricing(
    model: str,
    overrides: dict[str, ModelPricingOverride],
) -> tuple[ModelPricing, CostSource]:
    override = overrides.get(model)
    if override is not None:
        return (
            ModelPricing(
                input_per_million_usd=override.input_per_million_usd,
                output_per_million_usd=override.output_per_million_usd,
            ),
            "override_estimate",
        )
    pricing = MODEL_PRICING_USD.get(model)
    if pricing is None:
        raise MissingModelPricing(
            f"No evaluation pricing for model {model!r}; provide an explicit override"
        )
    return pricing, "catalog_estimate"


def calculate_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    pricing: ModelPricing,
) -> float:
    return (
        input_tokens * pricing.input_per_million_usd
        + output_tokens * pricing.output_per_million_usd
    ) / 1_000_000


def build_model_usage(
    *,
    role: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: float,
    overrides: dict[str, ModelPricingOverride],
    provider_reported_cost_usd: float | None = None,
) -> ModelUsage:
    if provider_reported_cost_usd is not None:
        cost_usd = provider_reported_cost_usd
        cost_source: CostSource = "provider_reported"
    else:
        pricing, cost_source = resolve_pricing(model, overrides)
        cost_usd = calculate_cost_usd(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pricing=pricing,
        )
    return ModelUsage(
        role=role,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_usd=cost_usd,
        cost_source=cost_source,
        duration_ms=duration_ms,
    )


def estimate_max_call_cost(
    *,
    model: str,
    max_input_tokens: int,
    max_output_tokens: int,
    overrides: dict[str, ModelPricingOverride],
) -> float:
    pricing, _ = resolve_pricing(model, overrides)
    return calculate_cost_usd(
        input_tokens=max_input_tokens,
        output_tokens=max_output_tokens,
        pricing=pricing,
    )
