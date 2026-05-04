"""Pydantic models for portfolio settings + analysis run state."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PortfolioSettings(BaseModel):
    """User-set parameters for portfolio analysis. ALL fields required (no defaults)."""

    cash_balance: float = Field(gt=0, description="Available cash to deploy (USD)")
    risk_tolerance: Literal["conservative", "moderate", "aggressive"]
    max_position_pct: float = Field(
        ge=5.0, le=30.0, description="Max single-position size as % of cash"
    )


class PortfolioSettingsUpdate(BaseModel):
    """Partial-update variant — used by PUT to allow None fields, then validated."""

    cash_balance: float | None = None
    risk_tolerance: Literal["conservative", "moderate", "aggressive"] | None = None
    max_position_pct: float | None = None


class AnalysisRun(BaseModel):
    """Background task status doc — one per run_id."""

    run_id: Literal["holdings", "picks"]
    status: Literal["pending", "running", "done", "error"]
    started_at: datetime
    finished_at: datetime | None = None
    message: str | None = None
    result_count: int | None = None
    sectors: list[str] | None = None  # picks only


class SectorUniverseRow(BaseModel):
    symbol: str
    name: str
    sector: str
    industry: str
    market_cap_b: float
