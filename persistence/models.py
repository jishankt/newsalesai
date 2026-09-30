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
"""

