"""
Production Circuit Breaker for LLM and External Services.

Provides resilience against cascading latency and downtime:
- CLOSED: Normal operation. Successes reset failure count.
- OPEN: After N consecutive failures, trips immediately without waiting for timeouts.
- HALF_OPEN: After recovery cooldown, permits a single trial probe to test recovery.
"""

import time
import logging
import threading
from enum import Enum
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger("security.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while circuit is open."""
    pass


class CircuitBreaker:
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 3,
        recovery_timeout: float = 15.0,
        half_open_success_threshold: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._last_error = None
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if (time.time() - self._last_failure_time) >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info(f"CircuitBreaker '{self.name}': Cooldown elapsed ({self.recovery_timeout}s). Transitioning to HALF_OPEN.")
            return self._state

    def is_available(self) -> bool:
        """Returns True if the circuit will allow a request right now."""
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def allow_request(self) -> bool:
        """Checks whether an execution should proceed or be rejected immediately."""
        with self._lock:
            cur = self.state
            if cur == CircuitState.CLOSED:
                return True
            if cur == CircuitState.HALF_OPEN:
                return True
            return False

    def record_success(self):
        """Records a successful external call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._last_error = None
                    logger.info(f"CircuitBreaker '{self.name}': Health probe succeeded. Circuit CLOSED.")
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0
                self._last_error = None

    def record_failure(self, error: Optional[Exception | str] = None):
        """Records a failed external call."""
        with self._lock:
            self._last_failure_time = time.time()
            self._last_error = str(error) if error else "Unknown failure"

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._success_count = 0
                logger.warning(f"CircuitBreaker '{self.name}': Probe failed ({self._last_error}). Re-opening circuit for {self.recovery_timeout}s.")
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                logger.warning(f"CircuitBreaker '{self.name}': Failure {self._failure_count}/{self.failure_threshold}: {self._last_error}")
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.error(f"CircuitBreaker '{self.name}': Failure threshold reached ({self._failure_count}). Circuit tripped to OPEN.")

    def reset(self):
        """Manually resets circuit breaker to CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = 0.0
            self._last_error = None

    def get_status(self) -> Dict[str, Any]:
        """Returns diagnostic state snapshot."""
        with self._lock:
            cur_state = self.state
            return {
                "name": self.name,
                "state": cur_state.value,
                "is_available": self.is_available(),
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure_time": self._last_failure_time,
                "last_error": self._last_error,
            }

    def __call__(self, func: Callable):
        """Decorator supporting automatic circuit-breaking around calls."""
        def wrapper(*args, **kwargs):
            if not self.allow_request():
                raise CircuitBreakerOpenException(
                    f"CircuitBreaker '{self.name}' is OPEN. Fast-failing request."
                )
            try:
                res = func(*args, **kwargs)
                self.record_success()
                return res
            except Exception as e:
                self.record_failure(e)
                raise
        return wrapper
