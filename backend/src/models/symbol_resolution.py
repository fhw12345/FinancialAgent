"""Typed contracts for stock-symbol search and clarification."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

SymbolResolutionStatus = Literal["resolved", "ambiguous", "unresolved"]
SymbolResolutionSource = Literal[
    "ui_context",
    "explicit_ticker",
    "local_directory",
    "provider_search",
    "llm_assisted",
]


class SymbolCandidate(BaseModel):
    """One validated US-equity symbol candidate."""

    symbol: str
    name: str
    exchange: str = ""
    type: str = "Equity"
    match_type: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SymbolResolution(BaseModel):
    """Result of resolving a research request to a validated symbol."""

    status: SymbolResolutionStatus
    source: SymbolResolutionSource
    reason_code: str
    symbol: str | None = None
    company_name: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    candidates: list[SymbolCandidate] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_status_payload(self) -> "SymbolResolution":
        """Keep control-flow states internally consistent."""
        if self.status == "resolved" and not self.symbol:
            raise ValueError("resolved symbol resolution requires symbol")
        if self.status == "ambiguous" and len(self.candidates) < 2:
            raise ValueError("ambiguous symbol resolution requires two candidates")
        if self.status == "unresolved" and self.symbol is not None:
            raise ValueError("unresolved symbol resolution cannot select a symbol")
        return self
