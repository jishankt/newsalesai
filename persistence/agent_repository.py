"""
SQLite Sales Agent Repository for Kepler Tech Conversational AI.
Manages salesman and admin agent accounts, credential verification, and status.
"""

import sqlite3
import os
import time
import uuid
import logging
from typing import Dict, Any, List, Optional
from werkzeug.security import generate_password_hash, check_password_hash

from persistence.models import CREATE_TABLES_SQL, AgentRecord

logger = logging.getLogger("persistence.agent_repository")

DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "conversations.db")


class AgentRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes tables and seeds default admin and salesman accounts if empty."""
        try:
            with self._get_connection() as conn:
                conn.executescript(CREATE_TABLES_SQL)
                conn.commit()

                # Check if agents table is empty, seed defaults
                cursor = conn.execute("SELECT COUNT(*) FROM sales_agents")
                count = cursor.fetchone()[0]
                if count == 0:
                    self._seed_default_agents(conn)
        except Exception as e:
            logger.error(f"Failed to initialize agent database at {self.db_path}: {e}")

    def _seed_default_agents(self, conn: sqlite3.Connection):
        """Seeds initial admin and salesman accounts."""
        now = time.time()
        agents = [
            (
                "agent-admin-01",
                "admin",
                "Operations Admin",
                "admin@keplertech.ae",
                generate_password_hash("admin123"),
                "admin",
                "active",
                "offline",
                now,
            ),
            (
                "agent-sales-01",
                "sales",
                "Tariq - Sales Specialist",
                "tariq.sales@keplertech.ae",
                generate_password_hash("sales123"),
                "salesman",
                "active",
                "offline",
                now,
            ),
        ]
        conn.executemany(
            """
            INSERT INTO sales_agents (agent_id, username, name, email, password_hash, role, status, online_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            agents,
        )
        conn.commit()
        logger.info("Seeded default admin and salesman accounts.")

    def authenticate(self, username: str, password: str) -> Optional[AgentRecord]:
        """Validates agent credentials and returns AgentRecord on success."""
        username_clean = (username or "").strip().lower()
        if not username_clean or not password:
            return None

        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM sales_agents WHERE LOWER(username) = ? AND status = 'active'",
                    (username_clean,),
                ).fetchone()

                if not row:
                    return None

                if check_password_hash(row["password_hash"], password):
                    now = time.time()
                    conn.execute(
                        "UPDATE sales_agents SET last_login = ?, online_status = 'online' WHERE agent_id = ?",
                        (now, row["agent_id"]),
                    )
                    conn.commit()
                    return self._row_to_record(row, last_login=now, online_status="online")
        except Exception as e:
            logger.error(f"Authentication error for {username_clean}: {e}")

        return None

    def create_agent(
        self,
        username: str,
        password: str,
        name: str,
        email: Optional[str] = None,
        role: str = "salesman",
    ) -> Optional[AgentRecord]:
        """Creates a new agent with hashed password. Raises ValueError if username exists."""
        username_clean = (username or "").strip().lower()
        name_clean = (name or "").strip()
        if not username_clean or not password or not name_clean:
            raise ValueError("Username, password, and name are required.")

        agent_id = f"agent-{uuid.uuid4().hex[:8]}"
        now = time.time()
        password_hash = generate_password_hash(password)
        role_clean = role if role in ("admin", "salesman") else "salesman"

        try:
            with self._get_connection() as conn:
                # Check duplicate
                existing = conn.execute(
                    "SELECT agent_id FROM sales_agents WHERE LOWER(username) = ?",
                    (username_clean,),
                ).fetchone()
                if existing:
                    raise ValueError(f"Username '{username_clean}' is already in use.")

                conn.execute(
                    """
                    INSERT INTO sales_agents (agent_id, username, name, email, password_hash, role, status, online_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', 'offline', ?)
                    """,
                    (agent_id, username_clean, name_clean, email or "", password_hash, role_clean, now),
                )
                conn.commit()

            return AgentRecord(
                agent_id=agent_id,
                username=username_clean,
                name=name_clean,
                email=email,
                password_hash=password_hash,
                role=role_clean,
                status="active",
                online_status="offline",
                created_at=now,
            )
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username_clean}' already exists.")
        except Exception as e:
            if not isinstance(e, ValueError):
                logger.error(f"Error creating agent {username_clean}: {e}")
            raise

    def get_by_id(self, agent_id: str) -> Optional[AgentRecord]:
        """Fetches agent by agent_id."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM sales_agents WHERE agent_id = ?", (agent_id,)
                ).fetchone()
                return self._row_to_record(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching agent {agent_id}: {e}")
            return None

    def get_by_username(self, username: str) -> Optional[AgentRecord]:
        """Fetches agent by username."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM sales_agents WHERE LOWER(username) = ?",
                    ((username or "").strip().lower(),),
                ).fetchone()
                return self._row_to_record(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching agent by username {username}: {e}")
            return None

    def list_agents(self) -> List[Dict[str, Any]]:
        """Returns all agents with activity metadata."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT agent_id, username, name, email, role, status, online_status, created_at, last_login FROM sales_agents ORDER BY created_at ASC"
                ).fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    d["account_status"] = d.get("status")
                    d["status"] = d.get("online_status") or "offline"
                    result.append(d)
                return result
        except Exception as e:
            logger.error(f"Error listing agents: {e}")
            return []

    def update_agent(
        self,
        agent_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        status: Optional[str] = None,
        role: Optional[str] = None,
        password: Optional[str] = None,
        online_status: Optional[str] = None,
    ) -> bool:
        """Updates agent record."""
        fields = []
        params = []
        if name is not None:
            fields.append("name = ?")
            params.append(name.strip())
        if email is not None:
            fields.append("email = ?")
            params.append(email.strip())
        if status is not None:
            if status in ("online", "busy", "offline"):
                fields.append("online_status = ?")
                params.append(status)
            elif status in ("active", "inactive"):
                fields.append("status = ?")
                params.append(status)
        if online_status is not None and online_status in ("online", "busy", "offline"):
            fields.append("online_status = ?")
            params.append(online_status)
        if role is not None and role in ("admin", "salesman"):
            fields.append("role = ?")
            params.append(role)
        if password:
            fields.append("password_hash = ?")
            params.append(generate_password_hash(password))

        if not fields:
            return False

        params.append(agent_id)
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    f"UPDATE sales_agents SET {', '.join(fields)} WHERE agent_id = ?",
                    params,
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating agent {agent_id}: {e}")
            return False

    def update_online_status(self, agent_id: str, online_status: str) -> bool:
        """Updates agent online presence (online, busy, offline)."""
        if online_status not in ("online", "busy", "offline"):
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "UPDATE sales_agents SET online_status = ? WHERE agent_id = ?",
                    (online_status, agent_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating online status for {agent_id}: {e}")
            return False

    def delete_agent(self, agent_id: str) -> bool:
        """Deletes an agent (prevents deleting last admin)."""
        try:
            with self._get_connection() as conn:
                # Prevent deleting last admin
                agent = self.get_by_id(agent_id)
                if agent and agent.role == "admin":
                    admin_count = conn.execute(
                        "SELECT COUNT(*) FROM sales_agents WHERE role = 'admin' AND status = 'active'"
                    ).fetchone()[0]
                    if admin_count <= 1:
                        raise ValueError("Cannot delete the only active admin account.")

                cursor = conn.execute("DELETE FROM sales_agents WHERE agent_id = ?", (agent_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            if not isinstance(e, ValueError):
                logger.error(f"Error deleting agent {agent_id}: {e}")
            raise

    def _row_to_record(self, row: sqlite3.Row, **overrides) -> AgentRecord:
        data = dict(row)
        data.update(overrides)
        return AgentRecord(
            agent_id=data["agent_id"],
            username=data["username"],
            name=data["name"],
            email=data.get("email"),
            password_hash=data["password_hash"],
            role=data.get("role", "salesman"),
            status=data.get("status", "active"),
            online_status=data.get("online_status", "offline"),
            created_at=data["created_at"],
            last_login=data.get("last_login"),
        )


# Global singleton instance
agent_repository = AgentRepository()
