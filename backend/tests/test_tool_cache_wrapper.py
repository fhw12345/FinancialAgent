"""
Unit tests for ToolCacheWrapper.

Tests caching, execution tracking, timeout handling, and circuit breaker integration.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.services.tool_cache_wrapper import ToolCacheWrapper

# ===== Fixtures =====


@pytest.fixture
def mock_redis_cache():
    """Mock Redis cache."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


@pytest.fixture
def mock_tool_execution_repo():
    """Mock tool execution repository."""
    repo = AsyncMock()
    repo.create = AsyncMock()
    return repo


@pytest.fixture
def wrapper(mock_redis_cache, mock_tool_execution_repo):
    """Create ToolCacheWrapper with mocked dependencies."""
    return ToolCacheWrapper(
        redis_cache=mock_redis_cache,
        tool_execution_repo=mock_tool_execution_repo,
    )


# ===== Constants Tests =====


class TestToolCacheWrapperConstants:
    """Test ToolCacheWrapper class constants."""

    def test_default_timeout(self):
        """Test default timeout is 30 seconds."""
        assert ToolCacheWrapper.DEFAULT_TIMEOUT_SECONDS == 30

    def test_tool_timeouts_news_sentiment(self):
        """Test NEWS_SENTIMENT has longer timeout."""
        assert ToolCacheWrapper.TOOL_TIMEOUTS["NEWS_SENTIMENT"] == 45
        assert ToolCacheWrapper.TOOL_TIMEOUTS["news_sentiment_tool"] == 45

    def test_tool_timeouts_fundamentals(self):
        """Test fundamental tools have 40s timeout."""
        assert ToolCacheWrapper.TOOL_TIMEOUTS["INCOME_STATEMENT"] == 40
        assert ToolCacheWrapper.TOOL_TIMEOUTS["BALANCE_SHEET"] == 40
        assert ToolCacheWrapper.TOOL_TIMEOUTS["CASH_FLOW"] == 40
        assert ToolCacheWrapper.TOOL_TIMEOUTS["EARNINGS"] == 40

    def test_tool_timeouts_technical(self):
        """Test technical indicator tools have 35s timeout."""
        assert ToolCacheWrapper.TOOL_TIMEOUTS["TIME_SERIES_INTRADAY"] == 35
        assert ToolCacheWrapper.TOOL_TIMEOUTS["TIME_SERIES_DAILY"] == 35

    def test_tool_timeouts_quote(self):
        """Test quote tools have shorter timeout."""
        assert ToolCacheWrapper.TOOL_TIMEOUTS["GLOBAL_QUOTE"] == 20
        assert ToolCacheWrapper.TOOL_TIMEOUTS["REALTIME_BULK_QUOTES"] == 25

    def test_tool_timeouts_local(self):
        """Test local analysis tools have shortest timeout."""
        assert ToolCacheWrapper.TOOL_TIMEOUTS["fibonacci_analysis_tool"] == 15
        assert ToolCacheWrapper.TOOL_TIMEOUTS["stochastic_analysis_tool"] == 15
        assert ToolCacheWrapper.TOOL_TIMEOUTS["macro_analysis_tool"] == 20


# ===== get_timeout_for_tool Tests =====


class TestGetTimeoutForTool:
    """Test get_timeout_for_tool method."""

    def test_known_tool_returns_specific_timeout(self, wrapper):
        """Test known tool returns its specific timeout."""
        assert wrapper.get_timeout_for_tool("NEWS_SENTIMENT") == 45
        assert wrapper.get_timeout_for_tool("GLOBAL_QUOTE") == 20

    def test_unknown_tool_returns_default(self, wrapper):
        """Test unknown tool returns default timeout."""
        assert wrapper.get_timeout_for_tool("unknown_tool") == 30
        assert wrapper.get_timeout_for_tool("custom_tool_xyz") == 30


# ===== wrap_tool Circuit Breaker Tests =====


class TestWrapToolCircuitBreaker:
    """Test wrap_tool circuit breaker integration."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_blocks_tool(
        self, wrapper, mock_tool_execution_repo
    ):
        """Test tool blocked when circuit breaker is open."""
        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = False
            mock_breaker.get_status.return_value = {
                "state": "open",
                "consecutive_failures": 5,
            }

            async def mock_tool(**kwargs):
                return {"data": "value"}

            result = await wrapper.wrap_tool(
                tool_name="GLOBAL_QUOTE",
                tool_source="mcp_alphavantage",
                tool_func=mock_tool,
                params={"symbol": "AAPL"},
                analysis_id="analysis_123",
                chat_id="chat_123",
                user_id="user_123",
            )

            assert result["circuit_breaker_open"] is True
            assert result["cache_hit"] is False
            assert "temporarily unavailable" in result["result"]["error"]
            assert result["result"]["fallback"] is True
            mock_tool_execution_repo.create.assert_called_once()


# ===== wrap_tool Cache Hit Tests =====


class TestWrapToolCacheHit:
    """Test wrap_tool cache hit behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_result(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test cache hit returns cached result without calling tool."""
        cached_data = {"symbol": "AAPL", "price": 150.0}
        mock_redis_cache.get.return_value = cached_data

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key"
            ) as mock_key:
                mock_key.return_value = "cache_key_123"

                tool_called = False

                async def mock_tool(**kwargs):
                    nonlocal tool_called
                    tool_called = True
                    return {"new": "data"}

                result = await wrapper.wrap_tool(
                    tool_name="GLOBAL_QUOTE",
                    tool_source="mcp_alphavantage",
                    tool_func=mock_tool,
                    params={"symbol": "AAPL"},
                    analysis_id="analysis_123",
                    chat_id="chat_123",
                    user_id="user_123",
                )

                assert result["cache_hit"] is True
                assert result["result"] == cached_data
                assert result["api_cost"] == 0.0
                assert tool_called is False
                mock_redis_cache.get.assert_called_once()
                mock_tool_execution_repo.create.assert_called_once()


# ===== wrap_tool Cache Miss Tests =====


class TestWrapToolCacheMiss:
    """Test wrap_tool cache miss behavior."""

    @pytest.mark.asyncio
    async def test_cache_miss_executes_tool(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test cache miss executes tool and caches result."""
        mock_redis_cache.get.return_value = None
        tool_result = {"symbol": "AAPL", "price": 155.0}

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key"
            ) as mock_key:
                mock_key.return_value = "cache_key_456"

                with patch("src.services.tool_cache_wrapper.get_api_cost") as mock_cost:
                    mock_cost.return_value = 0.0001

                    with patch(
                        "src.services.tool_cache_wrapper.get_tool_ttl"
                    ) as mock_ttl:
                        mock_ttl.return_value = 3600

                        async def mock_tool(**kwargs):
                            return tool_result

                        result = await wrapper.wrap_tool(
                            tool_name="GLOBAL_QUOTE",
                            tool_source="mcp_alphavantage",
                            tool_func=mock_tool,
                            params={"symbol": "AAPL"},
                            analysis_id="analysis_123",
                            chat_id="chat_123",
                            user_id="user_123",
                        )

                        assert result["cache_hit"] is False
                        assert result["result"] == tool_result
                        assert result["api_cost"] == 0.0001
                        mock_redis_cache.set.assert_called_once()
                        mock_breaker.record_success.assert_called_once_with(
                            "GLOBAL_QUOTE"
                        )

    @pytest.mark.asyncio
    async def test_sync_tool_execution(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test synchronous tool execution."""
        mock_redis_cache.get.return_value = None
        tool_result = {"data": "sync_result"}

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key",
                return_value="sync_tool_cache_key",
            ):
                with patch(
                    "src.services.tool_cache_wrapper.get_api_cost", return_value=0.0
                ):
                    with patch(
                        "src.services.tool_cache_wrapper.get_tool_ttl",
                        return_value=3600,
                    ):
                        # Create a sync function (not async)
                        def sync_tool(**kwargs):
                            return tool_result

                        result = await wrapper.wrap_tool(
                            tool_name="local_tool",
                            tool_source="1st_party",
                            tool_func=sync_tool,
                            params={"param": "value"},
                            analysis_id="analysis_123",
                            chat_id="chat_123",
                            user_id="user_123",
                        )

                        assert result["result"] == tool_result
                        assert result["cache_hit"] is False


# ===== wrap_tool Timeout Tests =====


class TestWrapToolTimeout:
    """Test wrap_tool timeout handling."""

    @pytest.mark.asyncio
    async def test_timeout_returns_fallback(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test timeout returns graceful fallback."""
        mock_redis_cache.get.return_value = None

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key",
                return_value="timeout_cache_key",
            ):
                # Create a slow tool that will timeout
                async def slow_tool(**kwargs):
                    await asyncio.sleep(100)  # Will never complete
                    return {"data": "value"}

                # Patch to use a very short timeout
                with patch.object(wrapper, "get_timeout_for_tool", return_value=0.01):
                    result = await wrapper.wrap_tool(
                        tool_name="SLOW_TOOL",
                        tool_source="mcp_slow",
                        tool_func=slow_tool,
                        params={"param": "value"},
                        analysis_id="analysis_123",
                        chat_id="chat_123",
                        user_id="user_123",
                    )

                    assert result["timeout"] is True
                    assert result["cache_hit"] is False
                    assert "fallback" in result["result"]
                    assert result["result"]["fallback"] is True
                    mock_breaker.record_failure.assert_called_once()


# ===== wrap_tool Error Tests =====


class TestWrapToolError:
    """Test wrap_tool error handling."""

    @pytest.mark.asyncio
    async def test_tool_exception_records_failure(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test tool exception records failure with circuit breaker."""
        mock_redis_cache.get.return_value = None

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key",
                return_value="test_cache_key",
            ):

                async def failing_tool(**kwargs):
                    raise ValueError("API Error")

                with pytest.raises(ValueError, match="API Error"):
                    await wrapper.wrap_tool(
                        tool_name="FAILING_TOOL",
                        tool_source="mcp_api",
                        tool_func=failing_tool,
                        params={"param": "value"},
                        analysis_id="analysis_123",
                        chat_id="chat_123",
                        user_id="user_123",
                    )

                mock_breaker.record_failure.assert_called_once()
                mock_tool_execution_repo.create.assert_called_once()


# ===== wrap_tool Execution ID Tests =====


class TestWrapToolExecutionId:
    """Test wrap_tool execution ID generation."""

    @pytest.mark.asyncio
    async def test_execution_id_format(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test execution ID has correct format."""
        mock_redis_cache.get.return_value = {"cached": True}

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key",
                return_value="exec_id_cache_key",
            ):

                async def mock_tool(**kwargs):
                    return {}

                result = await wrapper.wrap_tool(
                    tool_name="TEST_TOOL",
                    tool_source="1st_party",
                    tool_func=mock_tool,
                    params={},
                    analysis_id="analysis_123",
                    chat_id="chat_123",
                    user_id="user_123",
                )

                assert result["execution_id"].startswith("exec_")
                assert len(result["execution_id"]) == 17  # "exec_" + 12 hex chars


# ===== wrap_tool Paid API Detection Tests =====


class TestWrapToolPaidApiDetection:
    """Test wrap_tool paid API detection."""

    @pytest.mark.asyncio
    async def test_mcp_source_is_paid_api(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test mcp_ prefixed sources are marked as paid API."""
        mock_redis_cache.get.return_value = {"data": "cached"}

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key",
                return_value="paid_api_cache_key",
            ):

                async def mock_tool(**kwargs):
                    return {}

                await wrapper.wrap_tool(
                    tool_name="API_TOOL",
                    tool_source="mcp_alphavantage",
                    tool_func=mock_tool,
                    params={},
                    analysis_id="analysis_123",
                    chat_id="chat_123",
                    user_id="user_123",
                )

                # Check the execution record was created with is_paid_api=True
                call_args = mock_tool_execution_repo.create.call_args
                execution = call_args[0][0]
                assert execution.is_paid_api is True

    @pytest.mark.asyncio
    async def test_first_party_source_not_paid(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test 1st_party sources are not marked as paid API."""
        mock_redis_cache.get.return_value = {"data": "cached"}

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key",
                return_value="local_cache_key",
            ):

                async def mock_tool(**kwargs):
                    return {}

                await wrapper.wrap_tool(
                    tool_name="LOCAL_TOOL",
                    tool_source="1st_party",
                    tool_func=mock_tool,
                    params={},
                    analysis_id="analysis_123",
                    chat_id="chat_123",
                    user_id="user_123",
                )

                call_args = mock_tool_execution_repo.create.call_args
                execution = call_args[0][0]
                assert execution.is_paid_api is False


# ===== _store_execution Tests =====


class TestStoreExecution:
    """Test _store_execution method."""

    @pytest.mark.asyncio
    async def test_store_execution_creates_record(
        self, wrapper, mock_tool_execution_repo
    ):
        """Test _store_execution creates execution record."""
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        await wrapper._store_execution(
            execution_id="exec_abc123",
            chat_id="chat_456",
            user_id="user_789",
            analysis_id="analysis_012",
            message_id="msg_345",
            tool_name="TEST_TOOL",
            tool_source="1st_party",
            input_params={"symbol": "AAPL"},
            output_result={"price": 150.0},
            status="success",
            started_at=start_time,
            duration_ms=1234,
            is_paid_api=False,
            api_cost=0.0,
            cache_hit=False,
            cache_key="test_cache_key",
        )

        mock_tool_execution_repo.create.assert_called_once()
        execution = mock_tool_execution_repo.create.call_args[0][0]
        assert execution.execution_id == "exec_abc123"
        assert execution.tool_name == "TEST_TOOL"
        assert execution.status == "success"
        assert execution.duration_ms == 1234

    @pytest.mark.asyncio
    async def test_store_execution_with_error(self, wrapper, mock_tool_execution_repo):
        """Test _store_execution stores error message."""
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        await wrapper._store_execution(
            execution_id="exec_error123",
            chat_id="chat_456",
            user_id="user_789",
            analysis_id="analysis_012",
            message_id=None,
            tool_name="FAILING_TOOL",
            tool_source="mcp_api",
            input_params={},
            output_result={"error": "API Error"},
            status="error",
            started_at=start_time,
            duration_ms=500,
            is_paid_api=True,
            api_cost=0.0,
            cache_hit=False,
            cache_key="error_cache_key",
            error_message="API Error occurred",
        )

        execution = mock_tool_execution_repo.create.call_args[0][0]
        assert execution.status == "error"
        assert execution.error_message == "API Error occurred"
        assert execution.is_paid_api is True

    @pytest.mark.asyncio
    async def test_store_execution_handles_storage_failure(
        self, wrapper, mock_tool_execution_repo
    ):
        """Test _store_execution handles storage failure gracefully."""
        mock_tool_execution_repo.create.side_effect = Exception("Database error")
        start_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        # Should not raise - storage failure is logged but doesn't break execution
        await wrapper._store_execution(
            execution_id="exec_fail123",
            chat_id="chat_456",
            user_id="user_789",
            analysis_id="analysis_012",
            message_id=None,
            tool_name="TEST_TOOL",
            tool_source="1st_party",
            input_params={},
            output_result={},
            status="success",
            started_at=start_time,
            duration_ms=100,
            is_paid_api=False,
            api_cost=0.0,
            cache_hit=True,
            cache_key="test_key",
        )

        # Should have attempted to create
        mock_tool_execution_repo.create.assert_called_once()


# ===== Integration Tests =====


class TestToolCacheWrapperIntegration:
    """Integration tests for ToolCacheWrapper."""

    @pytest.mark.asyncio
    async def test_full_cache_miss_flow(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test complete cache miss flow: check cache → execute → store → cache."""
        mock_redis_cache.get.return_value = None
        tool_result = {"symbol": "TSLA", "price": 250.0}

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key"
            ) as mock_key:
                mock_key.return_value = "tsla_quote_key"

                with patch(
                    "src.services.tool_cache_wrapper.get_api_cost", return_value=0.00005
                ):
                    with patch(
                        "src.services.tool_cache_wrapper.get_tool_ttl", return_value=300
                    ):

                        async def quote_tool(**kwargs):
                            return tool_result

                        result = await wrapper.wrap_tool(
                            tool_name="GLOBAL_QUOTE",
                            tool_source="mcp_alphavantage",
                            tool_func=quote_tool,
                            params={"symbol": "TSLA"},
                            analysis_id="analysis_tsla",
                            chat_id="chat_abc",
                            user_id="user_def",
                            message_id="msg_ghi",
                        )

                        # Verify flow
                        mock_breaker.can_execute.assert_called_once_with("GLOBAL_QUOTE")
                        mock_redis_cache.get.assert_called_once_with("tsla_quote_key")
                        mock_redis_cache.set.assert_called_once_with(
                            "tsla_quote_key", tool_result, ttl_seconds=300
                        )
                        mock_breaker.record_success.assert_called_once_with(
                            "GLOBAL_QUOTE"
                        )
                        mock_tool_execution_repo.create.assert_called_once()

                        # Verify result
                        assert result["result"] == tool_result
                        assert result["cache_hit"] is False
                        assert result["api_cost"] == 0.00005
                        assert "execution_id" in result

    @pytest.mark.asyncio
    async def test_message_id_optional(
        self, wrapper, mock_redis_cache, mock_tool_execution_repo
    ):
        """Test message_id is optional."""
        mock_redis_cache.get.return_value = {"cached": True}

        with patch(
            "src.services.tool_cache_wrapper.tool_circuit_breaker"
        ) as mock_breaker:
            mock_breaker.can_execute.return_value = True

            with patch(
                "src.services.tool_cache_wrapper.generate_tool_cache_key",
                return_value="optional_msg_key",
            ):

                async def mock_tool(**kwargs):
                    return {}

                # Call without message_id
                result = await wrapper.wrap_tool(
                    tool_name="TEST_TOOL",
                    tool_source="1st_party",
                    tool_func=mock_tool,
                    params={},
                    analysis_id="analysis_123",
                    chat_id="chat_123",
                    user_id="user_123",
                    # message_id not provided
                )

                assert "execution_id" in result
                execution = mock_tool_execution_repo.create.call_args[0][0]
                assert execution.message_id is None
