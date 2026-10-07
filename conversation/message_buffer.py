"""
Session Message Aggregator & Buffer for WhatsApp & Web Chat in Kepler Tech SalesAI.

Buffers incoming rapid consecutive messages for a given session (default 5-8 seconds window),
aggregating multi-bubble inputs like:
  Message 1: "i want the media rolls for this"
  Message 2: "i need this magenta ink"
into a unified conversational prompt before dispatching to the orchestrator.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple, Any

# Configurable buffer aggregation window in seconds (default 5.0 seconds)
DEFAULT_BUFFER_WINDOW_SECONDS = 5.0


class MessageSessionBuffer:
    """Thread-safe session-level message buffer."""

    def __init__(self, window_seconds: float = DEFAULT_BUFFER_WINDOW_SECONDS):
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buffers: Dict[str, List[Tuple[float, str]]] = {}

    def add_message(self, session_id: str, message: str) -> None:
        """Adds a message to the session buffer with current timestamp."""
        clean_msg = (message or "").strip()
        if not clean_msg:
            return

        with self._lock:
            now = time.time()
            if session_id not in self._buffers:
                self._buffers[session_id] = []
            self._buffers[session_id].append((now, clean_msg))

    def get_and_clear(self, session_id: str) -> List[str]:
        """Retrieves and clears all buffered messages for the session."""
        with self._lock:
            if session_id not in self._buffers:
                return []
            entries = self._buffers.pop(session_id, [])
            return [msg for _, msg in entries]

    def get_combined_prompt(self, session_id: str, current_message: str) -> str:
        """
        Combines any previously buffered messages within the time window
        with current_message into a single aggregated thought.
        """
        clean_current = (current_message or "").strip()
        with self._lock:
            now = time.time()
            buffered = self._buffers.get(session_id, [])
            # Filter messages within window_seconds
            valid_msgs = [msg for t, msg in buffered if (now - t) <= self.window_seconds and msg != clean_current]
            # Clear expired or consumed
            self._buffers.pop(session_id, None)

        if valid_msgs:
            combined = valid_msgs + ([clean_current] if clean_current else [])
            return "\n".join(combined)

        return clean_current


# Global singleton instance
message_buffer = MessageSessionBuffer()
