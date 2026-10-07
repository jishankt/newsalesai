"""
Execution Trace for Kepler Tech SalesAI Workflow Engine.
Provides n8n-style visual and structured observability for every conversational turn.
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class TraceStep:
    name: str
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, SKIPPED, FAILED
    duration_ms: float = 0.0
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)

    def complete(self, summary: str = "", details: Optional[Dict[str, Any]] = None):
        self.status = "COMPLETED"
        self.duration_ms = round((time.time() - self.start_time) * 1000, 2)
        if summary:
            self.summary = summary
        if details:
            self.details.update(details)

    def fail(self, error_message: str):
        self.status = "FAILED"
        self.duration_ms = round((time.time() - self.start_time) * 1000, 2)
        self.summary = error_message
        self.details["error"] = error_message

    def skip(self, reason: str = ""):
        self.status = "SKIPPED"
        self.duration_ms = round((time.time() - self.start_time) * 1000, 2)
        self.summary = reason or "Skipped by pipeline condition"


class ExecutionTrace:
    """Collects and formats the end-to-end execution path for a turn."""

    def __init__(self):
        self.steps: List[TraceStep] = []
        self.start_time = time.time()
        self.total_duration_ms: float = 0.0

    def start_step(self, name: str) -> TraceStep:
        step = TraceStep(name=name, status="RUNNING", start_time=time.time())
        self.steps.append(step)
        return step

    def record_step(self, name: str, summary: str = "", details: Optional[Dict[str, Any]] = None, status: str = "COMPLETED"):
        step = TraceStep(
            name=name,
            status=status,
            summary=summary,
            details=details or {},
            duration_ms=0.0
        )
        self.steps.append(step)
        return step

    def finalize(self):
        self.total_duration_ms = round((time.time() - self.start_time) * 1000, 2)

    def to_list(self) -> List[Dict[str, Any]]:
        return [
            {
                "step": s.name,
                "status": s.status,
                "duration_ms": s.duration_ms,
                "summary": s.summary,
                "details": s.details,
            }
            for s in self.steps
        ]

    def render_ascii(self) -> str:
        """Renders an n8n-style textual checklist."""
        lines = []
        for s in self.steps:
            mark = "✓" if s.status == "COMPLETED" else ("✕" if s.status == "FAILED" else "○")
            lines.append(f"{mark} {s.name:<22} [{s.duration_ms:>6.1f}ms] {s.summary}")
        return "\n".join(lines)
