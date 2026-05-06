"""
Watchlist API endpoints for managing watched stocks.
"""

import asyncio
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from ..database.mongodb import MongoDB
from ..database.repositories.watchlist_repository import WatchlistRepository
from ..models.watchlist import WatchlistItem, WatchlistItemCreate
from ..services.alphavantage_market_data import AlphaVantageMarketDataService
from .dependencies.auth import get_mongodb, require_admin
from .dependencies.portfolio_deps import get_market_service
from .dependencies.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# Hard timeout per quote so a slow vendor never blocks the whole list response.
# 6s leaves enough room for cold-cache yfinance round-trips (Finnhub/AV are
# faster but we don't always pick them); cache hits return in ~5ms.
_QUOTE_TIMEOUT_SECONDS = 6.0


async def _enrich_with_live_quote(
    request: Request, items: list[WatchlistItem]
) -> list[WatchlistItem]:
    """Best-effort: parallel-fetch live quotes via DataManager and stamp
    transient `current_price` / `last_price_update` / `last_session` on each
    row. Single-symbol failures are swallowed (just leave the row unenriched);
    if DataManager is missing, returns the items untouched.

    Also coerces naive UTC datetimes (`added_at`, `last_analyzed_at`,
    `last_price_update`) to tz-aware so Pydantic emits "...+00:00" and the
    frontend's `new Date(iso)` correctly parses them as UTC instead of local.
    Same fix as HoldingResponse from_holding (v0.23.0).

    DataManager has its own redis cache (~30s on quotes), so repeated GETs
    don't actually hit the upstream vendor for every refresh."""
    # Pass 1: fix naive timestamps from Mongo Motor (BSON UTC → naive datetime)
    for it in items:
        if it.added_at is not None and it.added_at.tzinfo is None:
            it.added_at = it.added_at.replace(tzinfo=UTC)
        if it.last_analyzed_at is not None and it.last_analyzed_at.tzinfo is None:
            it.last_analyzed_at = it.last_analyzed_at.replace(tzinfo=UTC)

    dm = getattr(request.app.state, "data_manager", None)
    if dm is None or not items:
        return items

    async def _one(it: WatchlistItem) -> None:
        try:
            quote = await asyncio.wait_for(
                dm.get_quote(it.symbol), timeout=_QUOTE_TIMEOUT_SECONDS
            )
            price = float(getattr(quote, "price", 0) or 0)
            if price <= 0:
                return
            it.current_price = price
            it.last_price_update = datetime.now(UTC)
            sess = getattr(quote, "session", None)
            if sess:
                it.last_session = sess
        except (TimeoutError, Exception) as e:
            logger.warning(
                "watchlist_quote_enrichment_failed",
                symbol=it.symbol,
                error=str(e),
                error_type=type(e).__name__,
            )

    # Bound concurrency to avoid hammering vendor APIs on a long watchlist.
    sem = asyncio.Semaphore(8)

    async def _bounded(it: WatchlistItem) -> None:
        async with sem:
            await _one(it)

    await asyncio.gather(*(_bounded(it) for it in items))
    return items


@router.post("", response_model=WatchlistItem, status_code=201)
@limiter.limit("30/minute")
async def add_to_watchlist(
    request: Request,
    item: WatchlistItemCreate,
    _: None = Depends(require_admin),
    mongodb: MongoDB = Depends(get_mongodb),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> WatchlistItem:
    """Add a symbol to watchlist for automated analysis."""
    try:
        symbol_upper = item.symbol.upper()
        logger.info("Validating symbol before adding to watchlist", symbol=symbol_upper)

        try:
            search_results = await market_service.search_symbols(symbol_upper, limit=5)

            logger.debug(
                "Symbol search results",
                symbol=symbol_upper,
                results=[
                    {
                        "symbol": r.get("symbol"),
                        "name": r.get("name"),
                        "match_score": r.get("match_score"),
                    }
                    for r in search_results[:3]
                ],
            )

            exact_match = None
            for result in search_results:
                if result.get("symbol", "").upper() == symbol_upper:
                    exact_match = result
                    break

            if not exact_match and search_results:
                first_result = search_results[0]
                match_score = first_result.get("match_score", 0.0)
                if match_score >= 0.9:
                    logger.info(
                        "Using high-confidence match as fallback",
                        requested=symbol_upper,
                        matched=first_result.get("symbol"),
                        score=match_score,
                    )
                    exact_match = first_result

            if not exact_match:
                try:
                    quote = await market_service.get_quote(symbol_upper)
                    if quote and quote.get("price"):
                        logger.info(
                            "Symbol validated via GLOBAL_QUOTE fallback",
                            symbol=symbol_upper,
                            price=quote.get("price"),
                        )
                        exact_match = {
                            "symbol": symbol_upper,
                            "name": "Verified via real-time quote",
                        }
                except Exception as quote_error:
                    logger.debug(
                        "GLOBAL_QUOTE fallback failed",
                        symbol=symbol_upper,
                        error=str(quote_error),
                    )

            # Final fallback: use DataManager (Finnhub → AV → yfinance chain).
            # Catches symbols AV doesn't know (recent IPOs like CRWV) and
            # also survives AV rate-limiting.
            if not exact_match:
                dm = getattr(request.app.state, "data_manager", None)
                if dm is not None:
                    try:
                        q = await dm.get_quote(symbol_upper)
                        if q and getattr(q, "price", 0):
                            logger.info(
                                "Symbol validated via DataManager fallback chain",
                                symbol=symbol_upper,
                                price=q.price,
                            )
                            exact_match = {
                                "symbol": symbol_upper,
                                "name": "Verified via DataManager (Finnhub/AV/yfinance)",
                            }
                    except Exception as dm_error:
                        logger.debug(
                            "DataManager fallback failed",
                            symbol=symbol_upper,
                            error=str(dm_error),
                        )

            if not exact_match:
                logger.warning(
                    "Symbol validation failed - not found in market",
                    symbol=symbol_upper,
                    search_results_count=len(search_results),
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Symbol '{symbol_upper}' not found in market. Please verify the ticker symbol.",
                )

            company_name = exact_match.get("name", "Unknown")
            logger.info(
                "Symbol validated successfully",
                symbol=symbol_upper,
                company_name=company_name,
            )

        except HTTPException:
            raise
        except Exception as validation_error:
            logger.warning(
                "Symbol validation service unavailable - allowing symbol anyway",
                symbol=symbol_upper,
                error=str(validation_error),
                error_type=type(validation_error).__name__,
            )

        item.symbol = symbol_upper
        watchlist_collection = mongodb.get_collection("watchlist")
        watchlist_repo = WatchlistRepository(watchlist_collection)

        watchlist_item = await watchlist_repo.create(watchlist_create=item)

        logger.info(
            "Watchlist item added",
            symbol=watchlist_item.symbol,
            watchlist_id=watchlist_item.watchlist_id,
        )

        return watchlist_item

    except DuplicateKeyError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Symbol {item.symbol.upper()} is already in your watchlist",
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to add watchlist item",
            symbol=item.symbol,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to add symbol to watchlist. Please try again later.",
        ) from e


@router.get("", response_model=list[WatchlistItem])
@limiter.limit("60/minute")
async def get_watchlist(
    request: Request,
    mongodb: MongoDB = Depends(get_mongodb),
    skip: int = 0,
    limit: int = 50,
) -> list[WatchlistItem]:
    """Get watchlist with pagination."""
    if skip < 0:
        raise HTTPException(status_code=400, detail="skip must be >= 0")
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100")

    try:
        watchlist_collection = mongodb.get_collection("watchlist")
        watchlist_repo = WatchlistRepository(watchlist_collection)

        items = await watchlist_repo.get_by_user(skip=skip, limit=limit)

        # Best-effort live quote enrichment so the UI shows current price next
        # to each row. Failures are silent (row just renders without price).
        items = await _enrich_with_live_quote(request, items)

        logger.info(
            "Watchlist retrieved",
            count=len(items),
            skip=skip,
            limit=limit,
        )

        return items

    except Exception as e:
        logger.error(
            "Failed to get watchlist",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve watchlist. Please try again later.",
        ) from e


@router.delete("/{watchlist_id}", status_code=204)
@limiter.limit("30/minute")
async def remove_from_watchlist(
    request: Request,
    watchlist_id: str,
    _: None = Depends(require_admin),
    mongodb: MongoDB = Depends(get_mongodb),
) -> None:
    """Remove a symbol from watchlist."""
    try:
        watchlist_collection = mongodb.get_collection("watchlist")
        watchlist_repo = WatchlistRepository(watchlist_collection)

        deleted = await watchlist_repo.delete(watchlist_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Watchlist item not found")

        logger.info("Watchlist item removed", watchlist_id=watchlist_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to remove watchlist item",
            watchlist_id=watchlist_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to remove symbol from watchlist. Please try again later.",
        ) from e


@router.post("/analyze", status_code=202)
@limiter.limit("10/minute")
async def trigger_watchlist_analysis(
    request: Request,
    symbol: str | None = None,
    _: None = Depends(require_admin),
) -> dict:
    """Trigger analysis. Without `symbol`, analyzes the whole watchlist
    (force=True, skips already-held symbols). With `?symbol=BE`, runs the
    analysis for that single symbol regardless of whether it's in the
    watchlist or held — used by per-row "Analyze" buttons in the UI."""
    try:
        if not hasattr(request.app.state, "watchlist_analyzer"):
            raise HTTPException(
                status_code=500, detail="Watchlist analyzer not initialized"
            )

        analyzer = request.app.state.watchlist_analyzer

        if symbol:
            sym_upper = symbol.strip().upper()
            if not sym_upper or len(sym_upper) > 10 or not sym_upper.replace(".", "").isalnum():
                raise HTTPException(
                    status_code=400, detail=f"Invalid symbol: {symbol!r}"
                )
            logger.info("Single-symbol watchlist analysis triggered", symbol=sym_upper)
            success = await analyzer.analyze_symbol(sym_upper)
            return {
                "status": "analysis_completed" if success else "analysis_failed",
                "symbol": sym_upper,
            }

        logger.info("Manual watchlist analysis triggered (all symbols)")
        await analyzer.run_analysis_cycle(force=True)

        return {
            "status": "analysis_started",
            "message": "Watchlist analysis has been triggered",
        }

    except Exception as e:
        logger.error(
            "Failed to trigger watchlist analysis",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to trigger watchlist analysis. Please try again later.",
        ) from e
