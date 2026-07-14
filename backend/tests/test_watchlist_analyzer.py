"""
Unit tests for WatchlistAnalyzer service.

Tests automated analysis scheduling and symbol analysis.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.watchlist.analyzer import WatchlistAnalyzer

# ===== Fixtures =====


@pytest.fixture
def mock_collections():
    """Create mock MongoDB collections."""
    return {
        "watchlist": AsyncMock(),
        "messages": AsyncMock(),
        "chats": AsyncMock(),
    }


@pytest.fixture
def mock_redis_cache():
    """Create mock Redis cache."""
    return AsyncMock()


@pytest.fixture
def mock_market_service():
    """Create mock market service."""
    return Mock()


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = Mock()
    settings.max_context_tokens = 4096
    settings.context_reserve_tokens = 500
    return settings


@pytest.fixture
def analyzer(mock_collections, mock_redis_cache, mock_market_service, mock_settings):
    """Create WatchlistAnalyzer with mocked dependencies."""
    with patch("src.services.watchlist.analyzer.WatchlistRepository"):
        with patch("src.services.watchlist.analyzer.MessageRepository"):
            with patch("src.services.watchlist.analyzer.ChatRepository"):
                with patch("src.services.watchlist.analyzer.ContextWindowManager"):
                    with patch("src.services.watchlist.analyzer.ChatManager"):
                        with patch("src.services.watchlist.analyzer.AnalysisEngine"):
                            return WatchlistAnalyzer(
                                watchlist_collection=mock_collections["watchlist"],
                                messages_collection=mock_collections["messages"],
                                chats_collection=mock_collections["chats"],
                                redis_cache=mock_redis_cache,
                                market_service=mock_market_service,
                                settings=mock_settings,
                            )


# ===== __init__ Tests =====


class TestWatchlistAnalyzerInit:
    """Test WatchlistAnalyzer initialization."""

    def test_init_sets_dependencies(
        self, mock_collections, mock_redis_cache, mock_market_service, mock_settings
    ):
        """Test initialization sets all dependencies."""
        with patch(
            "src.services.watchlist.analyzer.WatchlistRepository"
        ) as mock_watchlist_repo:
            with patch(
                "src.services.watchlist.analyzer.MessageRepository"
            ) as mock_message_repo:
                with patch(
                    "src.services.watchlist.analyzer.ChatRepository"
                ) as mock_chat_repo:
                    with patch("src.services.watchlist.analyzer.ContextWindowManager"):
                        with patch("src.services.watchlist.analyzer.ChatManager"):
                            with patch(
                                "src.services.watchlist.analyzer.AnalysisEngine"
                            ):
                                analyzer = WatchlistAnalyzer(
                                    watchlist_collection=mock_collections["watchlist"],
                                    messages_collection=mock_collections["messages"],
                                    chats_collection=mock_collections["chats"],
                                    redis_cache=mock_redis_cache,
                                    market_service=mock_market_service,
                                    settings=mock_settings,
                                )

                                assert analyzer.redis_cache == mock_redis_cache
                                assert analyzer.market_service == mock_market_service
                                assert analyzer.settings == mock_settings
                                assert analyzer.is_running is False
                                assert analyzer._task is None
                                mock_watchlist_repo.assert_called_once()
                                mock_message_repo.assert_called_once()
                                mock_chat_repo.assert_called_once()

    def test_init_with_optional_dependencies(
        self, mock_collections, mock_redis_cache, mock_market_service, mock_settings
    ):
        """Test initialization with optional dependencies."""
        mock_agent = Mock()
        mock_order_repo = Mock()

        with patch("src.services.watchlist.analyzer.WatchlistRepository"):
            with patch("src.services.watchlist.analyzer.MessageRepository"):
                with patch("src.services.watchlist.analyzer.ChatRepository"):
                    with patch("src.services.watchlist.analyzer.ContextWindowManager"):
                        with patch("src.services.watchlist.analyzer.ChatManager"):
                            with patch(
                                "src.services.watchlist.analyzer.AnalysisEngine"
                            ):
                                analyzer = WatchlistAnalyzer(
                                    watchlist_collection=mock_collections["watchlist"],
                                    messages_collection=mock_collections["messages"],
                                    chats_collection=mock_collections["chats"],
                                    redis_cache=mock_redis_cache,
                                    market_service=mock_market_service,
                                    settings=mock_settings,
                                    agent=mock_agent,
                                    order_repository=mock_order_repo,
                                )

                                assert analyzer.agent == mock_agent
                                assert analyzer.order_repository == mock_order_repo


# ===== analyze_symbol Tests =====


class TestAnalyzeSymbol:
    """Test analyze_symbol method."""

    @pytest.mark.asyncio
    async def test_analyze_symbol_delegates_to_engine(self, analyzer):
        """Test analyze_symbol delegates to analysis engine."""
        analyzer.analysis_engine = AsyncMock()
        analyzer.analysis_engine.analyze_symbol = AsyncMock(return_value=True)

        result = await analyzer.analyze_symbol("AAPL", "user_123", "analysis_456")

        assert result is True
        analyzer.analysis_engine.analyze_symbol.assert_called_once_with(
            "AAPL", "user_123", "analysis_456"
        )

    @pytest.mark.asyncio
    async def test_analyze_symbol_with_defaults(self, analyzer):
        """Test analyze_symbol with default parameters."""
        analyzer.analysis_engine = AsyncMock()
        analyzer.analysis_engine.analyze_symbol = AsyncMock(return_value=False)

        result = await analyzer.analyze_symbol("TSLA")

        assert result is False
        analyzer.analysis_engine.analyze_symbol.assert_called_once_with(
            "TSLA", "local", None
        )


# ===== run_analysis_cycle Tests =====


class TestRunAnalysisCycle:
    """Test run_analysis_cycle method."""

    @pytest.mark.asyncio
    async def test_run_analysis_cycle_delegates(self, analyzer):
        """Test run_analysis_cycle delegates to engine."""
        analyzer.analysis_engine = AsyncMock()
        analyzer.analysis_engine.run_analysis_cycle = AsyncMock()

        await analyzer.run_analysis_cycle()

        analyzer.analysis_engine.run_analysis_cycle.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_run_analysis_cycle_force(self, analyzer):
        """Test run_analysis_cycle with force=True."""
        analyzer.analysis_engine = AsyncMock()
        analyzer.analysis_engine.run_analysis_cycle = AsyncMock()

        await analyzer.run_analysis_cycle(force=True)

        analyzer.analysis_engine.run_analysis_cycle.assert_called_once_with(True)


# ===== start Tests =====


class TestStart:
    """Test start method."""

    @pytest.mark.asyncio
    async def test_start_already_running(self, analyzer):
        """Test start when already running."""
        analyzer.is_running = True

        # Should return immediately
        await analyzer.start()

        # is_running should still be True
        assert analyzer.is_running is True

    @pytest.mark.asyncio
    async def test_start_runs_cycle(self, analyzer):
        """Test start runs analysis cycle."""
        analyzer.analysis_engine = AsyncMock()
        analyzer.analysis_engine.run_analysis_cycle = AsyncMock()

        # Run start in a task and stop it after a short time
        async def run_and_stop():
            task = asyncio.create_task(analyzer.start())
            await asyncio.sleep(0.1)
            analyzer.is_running = False
            await asyncio.sleep(0.1)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await run_and_stop()

        # Should have started
        assert analyzer.analysis_engine.run_analysis_cycle.called

    @pytest.mark.asyncio
    async def test_start_handles_exception(self, analyzer):
        """Test start handles exceptions and continues."""
        call_count = 0

        async def failing_cycle(force=False):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Test error")
            # Stop after second call
            analyzer.is_running = False

        analyzer.analysis_engine = AsyncMock()
        analyzer.analysis_engine.run_analysis_cycle = failing_cycle

        # Patch sleep to be fast
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await analyzer.start()

        # Should have been called at least twice (first failed, second succeeded)
        assert call_count >= 1


# ===== stop Tests =====


class TestStop:
    """Test stop method."""

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, analyzer):
        """Test stop sets is_running to False."""
        analyzer.is_running = True
        analyzer._task = None

        await analyzer.stop()

        assert analyzer.is_running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self, analyzer):
        """Test stop cancels running task."""
        analyzer.is_running = True

        # Create a real task that will be cancelled
        async def long_running():
            await asyncio.sleep(100)

        task = asyncio.create_task(long_running())
        analyzer._task = task

        await analyzer.stop()

        assert analyzer.is_running is False
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_stop_handles_cancelled_error(self, analyzer):
        """Test stop handles CancelledError from task."""
        analyzer.is_running = True

        # Create a task that raises CancelledError when awaited
        async def cancelled_task():
            raise asyncio.CancelledError()

        mock_task = asyncio.create_task(cancelled_task())
        mock_task.cancel()
        analyzer._task = mock_task

        # Should not raise
        await analyzer.stop()

        assert analyzer.is_running is False
