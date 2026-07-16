"""Unit tests for safe, validated Deep Agent symbol resolution."""

import pytest

from src.agent.symbol_resolver import LLMSymbolCandidates, SymbolResolver
from src.core.config import Settings
from src.models.symbol_resolution import SymbolCandidate


def candidate(
    symbol: str,
    *,
    name: str | None = None,
    confidence: float = 1.0,
    match_type: str = "exact_symbol",
) -> SymbolCandidate:
    return SymbolCandidate(
        symbol=symbol,
        name=name or symbol,
        confidence=confidence,
        match_type=match_type,
    )


class FakeSearchService:
    def __init__(
        self,
        *,
        exact: dict[str, SymbolCandidate] | None = None,
        searches: dict[str, list[SymbolCandidate]] | None = None,
    ) -> None:
        self.exact_results = exact or {}
        self.search_results = searches or {}
        self.exact_calls: list[str] = []
        self.search_calls: list[str] = []

    async def exact(self, symbol: str) -> SymbolCandidate | None:
        self.exact_calls.append(symbol)
        return self.exact_results.get(symbol)

    async def search(self, query: str, limit: int = 10) -> list[SymbolCandidate]:
        self.search_calls.append(query)
        return self.search_results.get(query, [])[:limit]


class FakeStructuredLLM:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def settings(*, llm_enabled: bool = True) -> Settings:
    return Settings(
        environment="test",
        symbol_resolution_llm_enabled=llm_enabled,
    )


@pytest.mark.asyncio
async def test_current_symbol_resolves_without_llm():
    search = FakeSearchService(exact={"NVDA": candidate("NVDA", name="NVIDIA")})
    llm = FakeStructuredLLM(error=AssertionError("LLM should not run"))
    resolver = SymbolResolver(search, settings=settings(), llm=llm)  # type: ignore[arg-type]

    result = await resolver.resolve(
        message="Analyze this company", current_symbol=" nvda "
    )

    assert result.status == "resolved"
    assert result.symbol == "NVDA"
    assert result.source == "ui_context"
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_invalid_current_symbol_falls_through_to_explicit_ticker():
    search = FakeSearchService(exact={"TSLA": candidate("TSLA", name="Tesla")})
    resolver = SymbolResolver(search, settings=settings(llm_enabled=False))  # type: ignore[arg-type]

    result = await resolver.resolve(
        message="Deeply analyze TSLA",
        current_symbol="not a symbol",
    )

    assert result.status == "resolved"
    assert result.symbol == "TSLA"
    assert result.source == "explicit_ticker"


@pytest.mark.asyncio
async def test_stop_word_is_not_treated_as_ticker():
    search = FakeSearchService()
    resolver = SymbolResolver(search, settings=settings(llm_enabled=False))  # type: ignore[arg-type]

    result = await resolver.resolve(
        message="Ask the CEO for a deep analysis",
        current_symbol=None,
    )

    assert result.status == "unresolved"
    assert "CEO" not in search.exact_calls


@pytest.mark.asyncio
async def test_invalid_explicit_ticker_does_not_get_reinterpreted():
    search = FakeSearchService()
    llm = FakeStructuredLLM(
        result=LLMSymbolCandidates(candidates=["AAPL"], query="Apple")
    )
    resolver = SymbolResolver(search, settings=settings(), llm=llm)  # type: ignore[arg-type]

    result = await resolver.resolve(
        message="Deeply analyze ZZZZZ",
        current_symbol=None,
    )

    assert result.status == "unresolved"
    assert result.reason_code == "symbol_not_found"
    assert result.symbol is None
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_two_valid_explicit_tickers_are_ambiguous():
    search = FakeSearchService(
        exact={
            "AAPL": candidate("AAPL", name="Apple"),
            "MSFT": candidate("MSFT", name="Microsoft"),
        }
    )
    resolver = SymbolResolver(search, settings=settings())  # type: ignore[arg-type]

    result = await resolver.resolve(
        message="Deeply analyze AAPL and MSFT",
        current_symbol=None,
    )

    assert result.status == "ambiguous"
    assert [item.symbol for item in result.candidates] == ["AAPL", "MSFT"]


@pytest.mark.asyncio
async def test_high_confidence_ranked_company_match_resolves():
    apple = candidate(
        "AAPL",
        name="Apple Inc.",
        confidence=0.95,
        match_type="exact_name",
    )
    search = FakeSearchService(searches={"Apple Inc.": [apple]})
    resolver = SymbolResolver(search, settings=settings())  # type: ignore[arg-type]

    result = await resolver.resolve(message="Apple Inc.", current_symbol=None)

    assert result.status == "resolved"
    assert result.symbol == "AAPL"
    assert result.source == "local_directory"


@pytest.mark.asyncio
async def test_close_ranked_candidates_require_clarification():
    search = FakeSearchService(
        searches={
            "Alpha": [
                candidate("AAA", confidence=0.9, match_type="symbol_prefix"),
                candidate("AAB", confidence=0.8, match_type="name_prefix"),
            ]
        }
    )
    resolver = SymbolResolver(search, settings=settings())  # type: ignore[arg-type]

    result = await resolver.resolve(message="Alpha", current_symbol=None)

    assert result.status == "ambiguous"
    assert result.reason_code == "ambiguous_symbol"


@pytest.mark.asyncio
async def test_llm_candidate_must_be_validated():
    search = FakeSearchService(exact={"BABA": candidate("BABA", name="Alibaba Group")})
    llm = FakeStructuredLLM(
        result=LLMSymbolCandidates(query="Alibaba", candidates=["BABA"])
    )
    resolver = SymbolResolver(search, settings=settings(), llm=llm)  # type: ignore[arg-type]

    result = await resolver.resolve(
        message="请深度分析阿里巴巴",
        current_symbol=None,
    )

    assert result.status == "resolved"
    assert result.symbol == "BABA"
    assert result.source == "llm_assisted"
    assert search.exact_calls == ["BABA"]


@pytest.mark.asyncio
async def test_llm_unknown_returns_unresolved_not_aapl():
    search = FakeSearchService()
    llm = FakeStructuredLLM(result=LLMSymbolCandidates())
    resolver = SymbolResolver(search, settings=settings(), llm=llm)  # type: ignore[arg-type]

    result = await resolver.resolve(
        message="请完整分析我昨天看到的那家公司",
        current_symbol=None,
    )

    assert result.status == "unresolved"
    assert result.symbol is None
    assert all(item.symbol != "AAPL" for item in result.candidates)


@pytest.mark.asyncio
async def test_llm_failure_returns_unresolved_not_aapl():
    search = FakeSearchService()
    llm = FakeStructuredLLM(error=TimeoutError("offline"))
    resolver = SymbolResolver(search, settings=settings(), llm=llm)  # type: ignore[arg-type]

    result = await resolver.resolve(
        message="请完整分析某家公司",
        current_symbol=None,
    )

    assert result.status == "unresolved"
    assert result.symbol is None


def test_symbol_normalization_supports_class_share_separators():
    assert SymbolResolver.normalize_symbol(" brk.b ") == "BRK.B"
    assert SymbolResolver.normalize_symbol("brk-b") == "BRK-B"
    assert SymbolResolver.normalize_symbol("BRK/B") is None
