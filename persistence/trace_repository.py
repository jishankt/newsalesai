"""
SQLite Execution Trace Repository for Kepler Tech SalesAI.
Stores and queries execution traces and node events for real-time and historical
n8n-style workflow visualization. Includes thread-safe in-memory pub-sub for SSE broadcasting.
"""

import sqlite3
import json
import os
import time
import uuid
import logging
import threading
import queue
from typing import Dict, Any, List, Optional, Tuple

from persistence.models import AgentExecutionTrace, AgentExecutionEvent, CREATE_TABLES_SQL

logger = logging.getLogger("persistence.trace_repository")

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "conversations.db")


class TraceEventBroadcaster:
    """Thread-safe event pub-sub for real-time Server-Sent Events (SSE)."""

    def __init__(self):
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def broadcast(self, event_type: str, data: Dict[str, Any]):
        payload = {"event": event_type, "data": data, "timestamp": time.time()}
        with self._lock:
            dead_queues = []
            for q in self._subscribers:
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    dead_queues.append(q)
            for q in dead_queues:
                if q in self._subscribers:
                    self._subscribers.remove(q)


broadcaster = TraceEventBroadcaster()
trace_broadcaster = broadcaster


class TraceRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                conn.executescript(CREATE_TABLES_SQL)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize trace tables at {self.db_path}: {e}")

    @staticmethod
    def _redact_text(text: Optional[str], max_len: int = 200) -> str:
        """Redacts sensitive credentials, tokens, and trims preview."""
        if not text:
            return ""
        s = str(text)
        # Redact credit cards, passwords, tokens
        import re
        s = re.sub(r"\b(?:\d[ -]*?){13,16}\b", "[REDACTED_CC]", s)
        s = re.sub(r"(?i)(password|secret|token|api[_-]?key)\s*[:=]\s*\S+", r"\1=[REDACTED]", s)
        if len(s) > max_len:
            return s[:max_len] + "…"
        return s

    def create_trace(
        self,
        conversation_id: str,
        session_id: str,
        message_id: str = "",
        correlation_id: str = "",
        input_preview: str = "",
    ) -> AgentExecutionTrace:
        """Initializes a new execution trace for a turn."""
        exec_id = f"exec_{uuid.uuid4().hex[:12]}"
        now = time.time()
        redacted_input = self._redact_text(input_preview)

        trace = AgentExecutionTrace(
            execution_id=exec_id,
            conversation_id=conversation_id,
            session_id=session_id,
            message_id=message_id,
            correlation_id=correlation_id,
            started_at=now,
            status="running",
            input_preview=redacted_input,
        )

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_execution_traces (
                        execution_id, conversation_id, session_id, message_id, correlation_id,
                        started_at, status, input_preview
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace.execution_id,
                        trace.conversation_id,
                        trace.session_id,
                        trace.message_id,
                        trace.correlation_id,
                        trace.started_at,
                        trace.status,
                        trace.input_preview,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to create execution trace {exec_id}: {e}")

        # Broadcast live event
        broadcaster.broadcast("trace_started", trace.to_dict())
        return trace

    def save_trace(self, trace: AgentExecutionTrace) -> AgentExecutionTrace:
        """Persists or replaces a full AgentExecutionTrace record."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_execution_traces (
                        execution_id, conversation_id, session_id, message_id, correlation_id,
                        started_at, completed_at, status, current_node_id, final_action,
                        final_response_status, total_duration_ms, error_code, summary,
                        input_preview, output_preview
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace.execution_id,
                        trace.conversation_id,
                        trace.session_id,
                        trace.message_id,
                        trace.correlation_id,
                        trace.started_at,
                        trace.completed_at,
                        trace.status,
                        trace.current_node_id,
                        trace.final_action,
                        trace.final_response_status,
                        trace.total_duration_ms,
                        trace.error_code,
                        trace.summary,
                        trace.input_preview,
                        trace.output_preview,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to save trace {trace.execution_id}: {e}")
        return trace

    def record_event(self, event: AgentExecutionEvent) -> AgentExecutionEvent:
        """Persists a pre-constructed AgentExecutionEvent."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_execution_events (
                        event_id, execution_id, node_id, node_type, event_type,
                        timestamp, duration_ms, status, input_summary, output_summary,
                        evidence_refs, tool_name, retry_count, error_metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.execution_id,
                        event.node_id,
                        event.node_type,
                        event.event_type,
                        event.timestamp,
                        event.duration_ms,
                        event.status,
                        event.input_summary,
                        event.output_summary,
                        event.evidence_refs,
                        event.tool_name,
                        event.retry_count,
                        event.error_metadata,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record event {event.event_id}: {e}")
        return event

    def record_node_event(
        self,
        execution_id: str,
        node_id: str,
        node_type: str,
        event_type: str,  # node_started, node_completed, node_failed, node_skipped
        duration_ms: float = 0.0,
        status: str = "completed",  # completed, failed, skipped, running
        input_summary: str = "",
        output_summary: str = "",
        evidence_refs: Optional[List[str]] = None,
        tool_name: Optional[str] = None,
        retry_count: int = 0,
        error_metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentExecutionEvent:
        """Records an immutable node event and updates trace current_node_id."""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now = time.time()
        ev_refs_json = json.dumps(evidence_refs or [])
        err_meta_json = json.dumps(error_metadata or {})

        event = AgentExecutionEvent(
            event_id=event_id,
            execution_id=execution_id,
            node_id=node_id,
            node_type=node_type,
            event_type=event_type,
            timestamp=now,
            duration_ms=round(duration_ms, 2),
            status=status,
            input_summary=self._redact_text(input_summary, 120),
            output_summary=self._redact_text(output_summary, 200),
            evidence_refs=ev_refs_json,
            tool_name=tool_name,
            retry_count=retry_count,
            error_metadata=err_meta_json,
        )

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_execution_events (
                        event_id, execution_id, node_id, node_type, event_type,
                        timestamp, duration_ms, status, input_summary, output_summary,
                        evidence_refs, tool_name, retry_count, error_metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.execution_id,
                        event.node_id,
                        event.node_type,
                        event.event_type,
                        event.timestamp,
                        event.duration_ms,
                        event.status,
                        event.input_summary,
                        event.output_summary,
                        event.evidence_refs,
                        event.tool_name,
                        event.retry_count,
                        event.error_metadata,
                    ),
                )
                conn.execute(
                    "UPDATE agent_execution_traces SET current_node_id = ? WHERE execution_id = ?",
                    (node_id, execution_id),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to record event for {execution_id}: {e}")

        # Broadcast live event
        broadcaster.broadcast("node_event", event.to_dict())
        return event

    def complete_trace(
        self,
        execution_id: str,
        status: str = "completed",  # completed, failed, handed_off, cancelled
        final_action: Optional[str] = None,
        final_response_status: Optional[str] = None,
        summary: str = "",
        output_preview: str = "",
        error_code: Optional[str] = None,
    ) -> Optional[AgentExecutionTrace]:
        """Finalizes an execution trace with terminal state and total duration."""
        now = time.time()
        redacted_output = self._redact_text(output_preview)

        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT started_at FROM agent_execution_traces WHERE execution_id = ?",
                    (execution_id,),
                ).fetchone()
                if not row:
                    return None

                started_at = row["started_at"]
                total_duration_ms = round((now - started_at) * 1000, 2)

                conn.execute(
                    """
                    UPDATE agent_execution_traces
                    SET completed_at = ?, status = ?, final_action = ?, final_response_status = ?,
                        total_duration_ms = ?, error_code = ?, summary = ?, output_preview = ?
                    WHERE execution_id = ?
                    """,
                    (
                        now,
                        status,
                        final_action,
                        final_response_status,
                        total_duration_ms,
                        error_code,
                        summary,
                        redacted_output,
                        execution_id,
                    ),
                )
                conn.commit()

            trace = self.get_trace(execution_id)
            if trace:
                broadcaster.broadcast("trace_completed", trace.to_dict())
            return trace
        except Exception as e:
            logger.error(f"Failed to complete execution trace {execution_id}: {e}")
            return None

    def get_trace(self, execution_id: str) -> Optional[AgentExecutionTrace]:
        """Fetches an execution trace by ID."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT execution_id, conversation_id, session_id, message_id, correlation_id,
                           started_at, completed_at, status, current_node_id, final_action,
                           final_response_status, total_duration_ms, error_code, summary,
                           input_preview, output_preview
                    FROM agent_execution_traces WHERE execution_id = ?
                    """,
                    (execution_id,),
                ).fetchone()
                if not row:
                    return None

                return AgentExecutionTrace(
                    execution_id=row["execution_id"],
                    conversation_id=row["conversation_id"],
                    session_id=row["session_id"],
                    message_id=row["message_id"] or "",
                    correlation_id=row["correlation_id"] or "",
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    status=row["status"],
                    current_node_id=row["current_node_id"],
                    final_action=row["final_action"],
                    final_response_status=row["final_response_status"],
                    total_duration_ms=row["total_duration_ms"] or 0.0,
                    error_code=row["error_code"],
                    summary=row["summary"] or "",
                    input_preview=row["input_preview"] or "",
                    output_preview=row["output_preview"] or "",
                )
        except Exception as e:
            logger.error(f"Failed to get trace {execution_id}: {e}")
            return None

    def get_trace_events(self, execution_id: str) -> List[AgentExecutionEvent]:
        """Fetches all events for an execution ordered chronologically."""
        events = []
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT event_id, execution_id, node_id, node_type, event_type,
                           timestamp, duration_ms, status, input_summary, output_summary,
                           evidence_refs, tool_name, retry_count, error_metadata
                    FROM agent_execution_events
                    WHERE execution_id = ?
                    ORDER BY timestamp ASC
                    """,
                    (execution_id,),
                ).fetchall()

                for r in rows:
                    events.append(
                        AgentExecutionEvent(
                            event_id=r["event_id"],
                            execution_id=r["execution_id"],
                            node_id=r["node_id"],
                            node_type=r["node_type"],
                            event_type=r["event_type"],
                            timestamp=r["timestamp"],
                            duration_ms=r["duration_ms"] or 0.0,
                            status=r["status"],
                            input_summary=r["input_summary"] or "",
                            output_summary=r["output_summary"] or "",
                            evidence_refs=r["evidence_refs"] or "[]",
                            tool_name=r["tool_name"],
                            retry_count=r["retry_count"] or 0,
                            error_metadata=r["error_metadata"] or "{}",
                        )
                    )
        except Exception as e:
            logger.error(f"Failed to get events for trace {execution_id}: {e}")
        return events

    # Alias for convenience
    get_events = get_trace_events

    def list_traces(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists execution traces for admin canvas dashboard."""
        results = []
        try:
            limit = min(limit, 200)
            query = (
                "SELECT execution_id, conversation_id, session_id, message_id, "
                "       started_at, completed_at, status, current_node_id, final_action, "
                "       final_response_status, total_duration_ms, summary, input_preview "
                "FROM agent_execution_traces WHERE 1=1"
            )
            params: List[Any] = []

            if status and status != "all":
                query += " AND status = ?"
                params.append(status)

            if search:
                query += " AND (execution_id LIKE ? OR session_id LIKE ? OR conversation_id LIKE ? OR input_preview LIKE ?)"
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param, search_param])

            query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            with self._get_connection() as conn:
                rows = conn.execute(query, params).fetchall()
                for r in rows:
                    results.append(
                        {
                            "execution_id": r["execution_id"],
                            "conversation_id": r["conversation_id"],
                            "session_id": r["session_id"],
                            "message_id": r["message_id"] or "",
                            "started_at": r["started_at"],
                            "completed_at": r["completed_at"],
                            "status": r["status"],
                            "current_node_id": r["current_node_id"],
                            "final_action": r["final_action"],
                            "final_response_status": r["final_response_status"],
                            "total_duration_ms": r["total_duration_ms"] or 0.0,
                            "summary": r["summary"] or "",
                            "input_preview": r["input_preview"] or "",
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to list traces: {e}")
        return results

    def count_traces(self, status: Optional[str] = None, search: Optional[str] = None) -> int:
        """Returns total count of matching traces."""
        try:
            query = "SELECT COUNT(*) FROM agent_execution_traces WHERE 1=1"
            params: List[Any] = []
            if status and status != "all":
                query += " AND status = ?"
                params.append(status)
            if search:
                query += " AND (execution_id LIKE ? OR session_id LIKE ? OR input_preview LIKE ?)"
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param])

            with self._get_connection() as conn:
                row = conn.execute(query, params).fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to count traces: {e}")
            return 0


trace_repository = TraceRepository()
