"""
Persistence Models and Table Definitions for Kepler Tech Conversational AI.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time


@dataclass
class SessionRecord:
    session_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    customer_name: Optional[str] = None
    state_json: str = "{}"
    history_json: str = "[]"
    version: int = 1


@dataclass
class LeadRecord:
    lead_id: Optional[int] = None
    session_id: str = ""
    created_at: float = field(default_factory=time.time)
    customer_name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    product_interest: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class AgentRecord:
    agent_id: str
    username: str
    name: str
    email: Optional[str] = None
    password_hash: str = ""
    role: str = "salesman"          # "admin" or "salesman"
    status: str = "active"          # "active" or "inactive"
    online_status: str = "offline"  # "online", "busy", "offline"
    created_at: float = field(default_factory=time.time)
    last_login: Optional[float] = None


@dataclass
class CustomerRecord:
    customer_id: str
    username: str
    display_name: str
    credential_hash: str
    phone: Optional[str] = None
    email: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_login: Optional[float] = None


@dataclass
class AgentExecutionTrace:
    execution_id: str
    conversation_id: str
    session_id: str
    started_at: float = field(default_factory=time.time)
    message_id: str = ""
    correlation_id: str = ""
    completed_at: Optional[float] = None
    status: str = "running"  # queued, running, completed, failed, handed_off, cancelled
    current_node_id: Optional[str] = None
    final_action: Optional[str] = None
    final_response_status: Optional[str] = None
    total_duration_ms: float = 0.0
    error_code: Optional[str] = None
    summary: str = ""
    input_preview: str = ""
    output_preview: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "current_node_id": self.current_node_id,
            "final_action": self.final_action,
            "final_response_status": self.final_response_status,
            "total_duration_ms": self.total_duration_ms,
            "error_code": self.error_code,
            "summary": self.summary,
            "input_preview": self.input_preview,
            "output_preview": self.output_preview,
        }


@dataclass
class AgentExecutionEvent:
    event_id: str
    execution_id: str
    node_id: str
    node_type: str
    event_type: str  # node_started, node_completed, node_failed, node_skipped
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    status: str = "completed"  # completed, failed, skipped, running
    input_summary: str = ""
    output_summary: str = ""
    evidence_refs: str = "[]"
    tool_name: Optional[str] = None
    retry_count: int = 0
    error_metadata: str = "{}"

    def to_dict(self) -> Dict[str, Any]:
        import json
        ev_refs = []
        try:
            ev_refs = json.loads(self.evidence_refs) if self.evidence_refs else []
        except Exception:
            ev_refs = [self.evidence_refs] if self.evidence_refs else []
        err_meta = {}
        try:
            err_meta = json.loads(self.error_metadata) if self.error_metadata else {}
        except Exception:
            err_meta = {"raw": self.error_metadata} if self.error_metadata else {}

        return {
            "event_id": self.event_id,
            "execution_id": self.execution_id,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "evidence_refs": ev_refs,
            "tool_name": self.tool_name,
            "retry_count": self.retry_count,
            "error_metadata": err_meta,
        }


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS conversation_sessions (
    session_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    customer_name TEXT,
    customer_id TEXT,
    state_json TEXT NOT NULL,
    history_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON conversation_sessions (updated_at);

CREATE TABLE IF NOT EXISTS commercial_leads (
    lead_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    customer_name TEXT,
    company TEXT,
    email TEXT,
    phone TEXT,
    product_interest TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_session ON commercial_leads (session_id);
CREATE INDEX IF NOT EXISTS idx_leads_created ON commercial_leads (created_at);

CREATE TABLE IF NOT EXISTS sales_agents (
    agent_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'salesman',
    status TEXT DEFAULT 'active',
    online_status TEXT DEFAULT 'offline',
    created_at REAL NOT NULL,
    last_login REAL
);
CREATE INDEX IF NOT EXISTS idx_agents_username ON sales_agents (username);

CREATE TABLE IF NOT EXISTS customer_profiles (
    customer_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    credential_hash TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    created_at REAL NOT NULL,
    last_login REAL
);
CREATE INDEX IF NOT EXISTS idx_customer_username ON customer_profiles (username);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    ip_address TEXT NOT NULL,
    success INTEGER NOT NULL,
    attempt_time REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_user_time ON login_attempts (username, attempt_time);
CREATE INDEX IF NOT EXISTS idx_login_ip_time ON login_attempts (ip_address, attempt_time);

CREATE TABLE IF NOT EXISTS agent_execution_traces (
    execution_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    message_id TEXT,
    correlation_id TEXT,
    started_at REAL NOT NULL,
    completed_at REAL,
    status TEXT NOT NULL DEFAULT 'running',
    current_node_id TEXT,
    final_action TEXT,
    final_response_status TEXT,
    total_duration_ms REAL DEFAULT 0.0,
    error_code TEXT,
    summary TEXT,
    input_preview TEXT,
    output_preview TEXT
);
CREATE INDEX IF NOT EXISTS idx_traces_conv ON agent_execution_traces (conversation_id);
CREATE INDEX IF NOT EXISTS idx_traces_started ON agent_execution_traces (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_traces_status ON agent_execution_traces (status);

CREATE TABLE IF NOT EXISTS agent_execution_events (
    event_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp REAL NOT NULL,
    duration_ms REAL DEFAULT 0.0,
    status TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    evidence_refs TEXT,
    tool_name TEXT,
    retry_count INTEGER DEFAULT 0,
    error_metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_exec ON agent_execution_events (execution_id, timestamp);
"""


