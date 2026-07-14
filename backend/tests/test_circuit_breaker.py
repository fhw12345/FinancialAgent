"""
Unit tests for CircuitBreaker pattern implementation.

Tests circuit breaker state transitions:
- CLOSED: Normal operation
- OPEN: Blocking requests after failure threshold
- HALF_OPEN: Testing recovery after timeout
"""

import time

from src.core.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    CircuitStats,
)

# ===== CircuitStats Tests =====


class TestCircuitStats:
    """Test CircuitStats dataclass"""

    def test_default_values(self):
        """Test default values are initialized correctly"""
        stats = CircuitStats()

        assert stats.failures == 0
        assert stats.successes == 0
        assert stats.last_failure_time == 0.0
        assert stats.state == CircuitState.CLOSED
        assert stats.consecutive_failures == 0
        assert stats.last_state_change > 0  # Should be set to current time


# ===== CircuitBreakerOpenError Tests =====


class TestCircuitBreakerOpenError:
    """Test CircuitBreakerOpenError exception"""

    def test_error_message_format(self):
        """Test error message is formatted correctly"""
        error = CircuitBreakerOpenError("test_tool", 30.5)

        assert error.tool_name == "test_tool"
        assert error.time_until_retry == 30.5
        assert "test_tool" in str(error)
        assert "30.5" in str(error)

    def test_error_is_exception(self):
        """Test that error is a proper exception"""
        error = CircuitBreakerOpenError("tool", 10.0)
        assert isinstance(error, Exception)


# ===== CircuitBreaker Basic Tests =====


class TestCircuitBreakerBasic:
    """Test basic CircuitBreaker functionality"""

    def test_default_initialization(self):
        """Test default parameter values"""
        breaker = CircuitBreaker()

        assert breaker.failure_threshold == 5
        assert breaker.recovery_timeout == 60.0
        assert breaker.success_threshold == 2

    def test_custom_initialization(self):
        """Test custom parameter values"""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30.0,
            success_threshold=1,
        )

        assert breaker.failure_threshold == 3
        assert breaker.recovery_timeout == 30.0
        assert breaker.success_threshold == 1

    def test_initial_state_is_closed(self):
        """Test that new circuits start in CLOSED state"""
        breaker = CircuitBreaker()

        status = breaker.get_status("new_tool")

        assert status["state"] == "closed"
        assert status["failures"] == 0
        assert status["successes"] == 0


# ===== can_execute Tests =====


class TestCanExecute:
    """Test can_execute method"""

    def test_can_execute_when_closed(self):
        """Test execution allowed when circuit is CLOSED"""
        breaker = CircuitBreaker()

        assert breaker.can_execute("tool_1") is True

    def test_cannot_execute_when_open(self):
        """Test execution blocked when circuit is OPEN"""
        breaker = CircuitBreaker(failure_threshold=2)

        # Trigger enough failures to open circuit
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        assert breaker.can_execute("tool_1") is False

    def test_can_execute_after_recovery_timeout(self):
        """Test execution allowed after recovery timeout (half-open)"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Open the circuit
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # Wait for recovery timeout
        time.sleep(0.15)

        # Should be able to execute (circuit is now half-open)
        assert breaker.can_execute("tool_1") is True


# ===== record_success Tests =====


class TestRecordSuccess:
    """Test record_success method"""

    def test_success_increments_counter(self):
        """Test success count is incremented"""
        breaker = CircuitBreaker()

        breaker.record_success("tool_1")
        breaker.record_success("tool_1")

        status = breaker.get_status("tool_1")
        assert status["successes"] == 2

    def test_success_resets_consecutive_failures(self):
        """Test that success resets consecutive failure counter"""
        breaker = CircuitBreaker()

        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")
        breaker.record_success("tool_1")

        status = breaker.get_status("tool_1")
        assert status["consecutive_failures"] == 0

    def test_success_in_half_open_closes_circuit(self):
        """Test that success in half-open state closes the circuit"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        # Open the circuit
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # Wait for half-open
        time.sleep(0.1)
        breaker.can_execute("tool_1")  # Triggers state update

        # Record success - should close circuit
        breaker.record_success("tool_1")

        status = breaker.get_status("tool_1")
        assert status["state"] == "closed"


# ===== record_failure Tests =====


class TestRecordFailure:
    """Test record_failure method"""

    def test_failure_increments_counters(self):
        """Test failure counts are incremented"""
        breaker = CircuitBreaker()

        breaker.record_failure("tool_1")

        status = breaker.get_status("tool_1")
        assert status["failures"] == 1
        assert status["consecutive_failures"] == 1

    def test_failure_threshold_opens_circuit(self):
        """Test that reaching failure threshold opens circuit"""
        breaker = CircuitBreaker(failure_threshold=3)

        # Record failures up to threshold
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # Still closed
        status = breaker.get_status("tool_1")
        assert status["state"] == "closed"

        # Third failure should open circuit
        breaker.record_failure("tool_1")

        status = breaker.get_status("tool_1")
        assert status["state"] == "open"

    def test_failure_in_half_open_reopens_circuit(self):
        """Test that failure in half-open immediately reopens circuit"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        # Open the circuit
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # Wait for half-open
        time.sleep(0.1)
        breaker.can_execute("tool_1")  # Triggers state update to half-open

        # Record failure - should reopen circuit
        breaker.record_failure("tool_1")

        status = breaker.get_status("tool_1")
        assert status["state"] == "open"

    def test_failure_with_error_object(self):
        """Test recording failure with error object"""
        breaker = CircuitBreaker()
        error = ValueError("Test error")

        # Should not raise
        breaker.record_failure("tool_1", error=error)

        status = breaker.get_status("tool_1")
        assert status["failures"] == 1


# ===== State Transition Tests =====


class TestStateTransitions:
    """Test circuit breaker state transitions"""

    def test_closed_to_open_transition(self):
        """Test CLOSED -> OPEN transition on failure threshold"""
        breaker = CircuitBreaker(failure_threshold=2)

        # Start in CLOSED
        status = breaker.get_status("tool_1")
        assert status["state"] == "closed"

        # Hit threshold
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # Now OPEN
        status = breaker.get_status("tool_1")
        assert status["state"] == "open"

    def test_open_to_half_open_transition(self):
        """Test OPEN -> HALF_OPEN transition after recovery timeout"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        # Open the circuit
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # Wait for recovery
        time.sleep(0.1)

        # Check can_execute to trigger state update
        result = breaker.can_execute("tool_1")

        # Should be HALF_OPEN and allow execution
        assert result is True
        status = breaker.get_status("tool_1")
        assert status["state"] == "half_open"

    def test_half_open_to_closed_transition(self):
        """Test HALF_OPEN -> CLOSED transition on success"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        # Open the circuit
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # Wait for half-open
        time.sleep(0.1)
        breaker.can_execute("tool_1")

        # Success should close
        breaker.record_success("tool_1")

        status = breaker.get_status("tool_1")
        assert status["state"] == "closed"

    def test_half_open_to_open_transition(self):
        """Test HALF_OPEN -> OPEN transition on failure"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        # Open the circuit
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # Wait for half-open
        time.sleep(0.1)
        breaker.can_execute("tool_1")

        # Failure should reopen
        breaker.record_failure("tool_1")

        status = breaker.get_status("tool_1")
        assert status["state"] == "open"


# ===== Multi-Tool Tests =====


class TestMultiTool:
    """Test circuit breaker with multiple tools"""

    def test_separate_circuits_per_tool(self):
        """Test that each tool has its own circuit"""
        breaker = CircuitBreaker(failure_threshold=2)

        # Fail tool_1
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # tool_1 should be OPEN
        assert breaker.can_execute("tool_1") is False

        # tool_2 should still be CLOSED
        assert breaker.can_execute("tool_2") is True

    def test_get_status_all_tools(self):
        """Test getting status for all tools"""
        breaker = CircuitBreaker()

        breaker.record_success("tool_1")
        breaker.record_failure("tool_2")

        status = breaker.get_status()

        assert "tool_1" in status
        assert "tool_2" in status
        assert status["tool_1"]["successes"] == 1
        assert status["tool_2"]["failures"] == 1


# ===== reset Tests =====


class TestReset:
    """Test reset method"""

    def test_reset_single_tool(self):
        """Test resetting a single tool's circuit"""
        breaker = CircuitBreaker(failure_threshold=2)

        # Open tool_1's circuit
        breaker.record_failure("tool_1")
        breaker.record_failure("tool_1")

        # Also fail tool_2 once
        breaker.record_failure("tool_2")

        # Reset only tool_1
        breaker.reset("tool_1")

        # tool_1 should be reset (closed, no history)
        assert breaker.can_execute("tool_1") is True
        status = breaker.get_status("tool_1")
        assert status["failures"] == 0

        # tool_2 should still have its failure
        status2 = breaker.get_status("tool_2")
        assert status2["failures"] == 1

    def test_reset_all_tools(self):
        """Test resetting all circuits"""
        breaker = CircuitBreaker()

        breaker.record_failure("tool_1")
        breaker.record_failure("tool_2")
        breaker.record_failure("tool_3")

        # Reset all
        breaker.reset()

        # All should be clean
        status = breaker.get_status()
        assert len(status) == 0

    def test_reset_nonexistent_tool(self):
        """Test resetting a tool that doesn't exist (should not raise)"""
        breaker = CircuitBreaker()

        # Should not raise
        breaker.reset("nonexistent_tool")


# ===== Integration Scenarios =====


class TestIntegrationScenarios:
    """Test real-world usage scenarios"""

    def test_intermittent_failures_dont_open_circuit(self):
        """Test that intermittent failures (with successes) don't open circuit"""
        breaker = CircuitBreaker(failure_threshold=3)

        # Alternating failures and successes
        breaker.record_failure("tool_1")
        breaker.record_success("tool_1")  # Resets consecutive failures
        breaker.record_failure("tool_1")
        breaker.record_success("tool_1")  # Resets again

        # Should still be CLOSED
        status = breaker.get_status("tool_1")
        assert status["state"] == "closed"

    def test_rapid_recovery_scenario(self):
        """Test rapid failure and recovery cycle"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        # First failure cycle
        breaker.record_failure("api")
        breaker.record_failure("api")
        assert breaker.can_execute("api") is False

        # Wait and recover
        time.sleep(0.1)
        assert breaker.can_execute("api") is True  # Half-open
        breaker.record_success("api")

        # Should be closed again
        status = breaker.get_status("api")
        assert status["state"] == "closed"

        # New failure cycle
        breaker.record_failure("api")
        breaker.record_failure("api")
        assert breaker.can_execute("api") is False
