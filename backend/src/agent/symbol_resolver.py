"""Resolve deep-research requests to validated stock symbols."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from ..core.config import Settings, get_settings
from ..models.symbol_resolution import (
    SymbolCandidate,
    SymbolResolution,
    SymbolResolutionSource,
)
from ..services.symbol_search_service import SymbolSearchService
from .llm_factory import get_llm
from .symbol_tokens import (
    extract_explicit_symbols,
    has_explicit_symbol_intent,
    normalize_symbol,
)

logger = structlog.get_logger()

_LLM_PROMPT = """Identify possible US stock ticker symbols in this request.

Return a short search query for the company name and at most three ticker
candidates. Return an empty candidate list when uncertain. Do not invent a
default symbol.

User request: {message}
"""


class LLMSymbolCandidates(BaseModel):
    """Structured candidate proposal from the lightweight resolver model."""

    query: str = ""
    candidates: list[str] = Field(default_factory=list, max_length=3)


class SymbolResolver:
    """Rules-first resolver with validated LLM-assisted candidates."""

    def __init__(
        self,
        search_service: SymbolSearchService,
        *,
        settings: Settings | None = None,
        llm: Any | None = None,
        auto_resolve_confidence: float = 0.9,
        minimum_margin: float = 0.15,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._search_service = search_service
        self._settings = settings or get_settings()
        self._llm = llm
        self._auto_resolve_confidence = auto_resolve_confidence
        self._minimum_margin = minimum_margin
        self._timeout_seconds = timeout_seconds

    async def resolve(
        self,
        *,
        message: str,
        current_symbol: str | None,
    ) -> SymbolResolution:
        """Resolve one request without ever selecting an unvalidated default."""
        started = time.perf_counter()

        explicit_symbols = self._extract_explicit_symbols(message)
        if explicit_symbols:
            validated = await self._validate_candidates(explicit_symbols)
            if len(validated) == 1:
                return self._resolved(
                    validated[0],
                    source="explicit_ticker",
                    reason_code="resolved_explicit_ticker",
                    started=started,
                )
            if len(validated) > 1:
                return self._ambiguous(
                    validated,
                    source="explicit_ticker",
                    reason_code="ambiguous_symbol",
                    started=started,
                )
            if current_symbol is None or has_explicit_symbol_intent(
                message,
                explicit_symbols,
            ):
                return self._unresolved(
                    source="explicit_ticker",
                    reason_code="symbol_not_found",
                    started=started,
                )

        if current_symbol:
            selected = self.normalize_symbol(current_symbol)
            if selected:
                candidate = await self._search_service.exact(selected)
                if candidate is not None:
                    return self._resolved(
                        candidate,
                        source="ui_context",
                        reason_code="resolved_ui_symbol",
                        started=started,
                    )

        deterministic = await self._search_service.search(message.strip(), limit=5)
        deterministic_decision = self._ranked_decision(
            deterministic,
            source="local_directory",
            started=started,
        )
        if deterministic_decision is not None:
            return deterministic_decision

        if not self._settings.symbol_resolution_llm_enabled:
            return self._unresolved(
                source="local_directory",
                reason_code="symbol_missing",
                candidates=deterministic,
                started=started,
            )

        llm_candidates = await self._propose_candidates(message)
        validated = await self._validate_candidates(llm_candidates.candidates)
        if len(validated) == 1:
            return self._resolved(
                validated[0],
                source="llm_assisted",
                reason_code="resolved_llm_candidate",
                started=started,
            )
        if len(validated) > 1:
            return self._ambiguous(
                validated,
                source="llm_assisted",
                reason_code="ambiguous_symbol",
                started=started,
            )

        if llm_candidates.query:
            searched = await self._search_service.search(
                llm_candidates.query,
                limit=5,
            )
            searched_decision = self._ranked_decision(
                searched,
                source="llm_assisted",
                started=started,
            )
            if searched_decision is not None:
                return searched_decision

        return self._unresolved(
            source="llm_assisted",
            reason_code="symbol_missing",
            candidates=deterministic,
            started=started,
        )

    @staticmethod
    def normalize_symbol(value: str) -> str | None:
        """Normalize case and whitespace while rejecting invalid punctuation."""
        return normalize_symbol(value)

    def _extract_explicit_symbols(self, message: str) -> list[str]:
        return extract_explicit_symbols(message)

    async def _validate_candidates(
        self,
        symbols: list[str],
    ) -> list[SymbolCandidate]:
        normalized = []
        for raw in symbols[:3]:
            symbol = self.normalize_symbol(raw)
            if symbol and symbol not in normalized:
                normalized.append(symbol)
        results = await asyncio.gather(
            *(self._search_service.exact(symbol) for symbol in normalized)
        )
        return [candidate for candidate in results if candidate is not None]

    async def _propose_candidates(self, message: str) -> LLMSymbolCandidates:
        llm = self._llm or get_llm(
            "router",
            temperature=0,
            max_tokens=120,
            timeout=self._timeout_seconds,
        )
        structured = llm.with_structured_output(LLMSymbolCandidates)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                result = await structured.ainvoke(
                    [HumanMessage(content=_LLM_PROMPT.format(message=message[:1000]))]
                )
            validated: LLMSymbolCandidates = LLMSymbolCandidates.model_validate(result)
            return validated
        except Exception as exc:
            logger.warning(
                "symbol_resolution_llm_failed",
                error=str(exc),
            )
            return LLMSymbolCandidates()

    def _ranked_decision(
        self,
        candidates: list[SymbolCandidate],
        *,
        source: SymbolResolutionSource,
        started: float,
    ) -> SymbolResolution | None:
        if not candidates:
            return None
        first = candidates[0]
        second_confidence = candidates[1].confidence if len(candidates) > 1 else 0.0
        if (
            first.confidence >= self._auto_resolve_confidence
            and first.confidence - second_confidence >= self._minimum_margin
        ):
            return self._resolved(
                first,
                source=source,
                reason_code="resolved_ranked_search",
                started=started,
            )
        if len(candidates) >= 2:
            return self._ambiguous(
                candidates,
                source=source,
                reason_code="ambiguous_symbol",
                started=started,
            )
        return None

    def _resolved(
        self,
        candidate: SymbolCandidate,
        *,
        source: SymbolResolutionSource,
        reason_code: str,
        started: float,
    ) -> SymbolResolution:
        resolution = SymbolResolution(
            status="resolved",
            source=source,
            reason_code=reason_code,
            symbol=candidate.symbol,
            company_name=candidate.name,
            confidence=candidate.confidence,
            candidates=[candidate],
        )
        self._log_resolution(resolution, started)
        return resolution

    def _ambiguous(
        self,
        candidates: list[SymbolCandidate],
        *,
        source: SymbolResolutionSource,
        reason_code: str,
        started: float,
    ) -> SymbolResolution:
        resolution = SymbolResolution(
            status="ambiguous",
            source=source,
            reason_code=reason_code,
            confidence=candidates[0].confidence,
            candidates=candidates[:5],
        )
        self._log_resolution(resolution, started)
        return resolution

    def _unresolved(
        self,
        *,
        source: SymbolResolutionSource,
        reason_code: str,
        started: float,
        candidates: list[SymbolCandidate] | None = None,
    ) -> SymbolResolution:
        resolution = SymbolResolution(
            status="unresolved",
            source=source,
            reason_code=reason_code,
            candidates=(candidates or [])[:5],
        )
        self._log_resolution(resolution, started)
        return resolution

    @staticmethod
    def _log_resolution(
        resolution: SymbolResolution,
        started: float,
    ) -> None:
        logger.info(
            "symbol_resolution_completed",
            resolution_status=resolution.status,
            resolution_source=resolution.source,
            reason_code=resolution.reason_code,
            selected_symbol=resolution.symbol,
            candidate_count=len(resolution.candidates),
            confidence=resolution.confidence,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
