from __future__ import annotations

from dataclasses import dataclass

from .live_schemas import ModelUsage


@dataclass
class BudgetLedger:
    max_cost_usd: float
    spent_usd: float = 0.0

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.max_cost_usd - self.spent_usd)

    def can_reserve(self, amount_usd: float) -> bool:
        return amount_usd <= self.remaining_usd

    def charge(self, usages: list[ModelUsage]) -> bool:
        self.spent_usd += sum(usage.cost_usd for usage in usages)
        return self.spent_usd <= self.max_cost_usd
