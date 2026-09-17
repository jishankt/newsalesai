"""
Admin API routes for Kepler Tech SalesAI Dashboard.
Provides session list, session detail (chat history), stats, and leads.
"""

import sqlite3
import json
import os
import time
import logging
from typing import Dict, Any, List, Optional
from flask import Blueprint, jsonify, request, render_template

logger = logging.getLogger("admin_routes")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "conversations.db")


def _conn():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


admin_bp = Blueprint("admin", __name__)


# ── Dashboard UI ────────────────────────────────────────────────────────────
@admin_bp.route("/admin")
@admin_bp.route("/admin/")
def admin_dashboard():
    return render_template("admin.html")


# ── API: Stats ───────────────────────────────────────────────────────────────
@admin_bp.route("/api/admin/stats")
def admin_stats():
    try:
        with _conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM conversation_sessions").fetchone()[0]
            today_ts = time.time() - 86400
            today = conn.execute(
                "SELECT COUNT(*) FROM conversation_sessions WHERE updated_at > ?", (today_ts,)
            ).fetchone()[0]
            active_1h = conn.execute(
                "SELECT COUNT(*) FROM conversation_sessions WHERE updated_at > ?",
                (time.time() - 3600,)
            ).fetchone()[0]
            leads_total = conn.execute("SELECT COUNT(*) FROM commercial_leads").fetchone()[0]
            leads_today = conn.execute(
                "SELECT COUNT(*) FROM commercial_leads WHERE created_at > ?", (today_ts,)
            ).fetchone()[0]
            # Category breakdown from state_json
            rows = conn.execute("SELECT state_json FROM conversation_sessions").fetchall()
            cats: Dict[str, int] = {}
            for r in rows:
                try:
                    s = json.loads(r["state_json"])
                    cat = s.get("category") or "unknown"
                    cats[cat] = cats.get(cat, 0) + 1
                except Exception:
                    pass

        return jsonify({
            "success": True,
            "total_sessions": total,
            "sessions_today": today,
            "active_last_hour": active_1h,
            "leads_total": leads_total,
            "leads_today": leads_today,
            "category_breakdown": cats,
        })
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── API: Session List ─────────────────────────────────────────────────────────
@admin_bp.route("/api/admin/sessions")
def admin_sessions():
    try:
        limit = min(int(request.args.get("limit", 50)), 500)
        offset = int(request.args.get("offset", 0))
        search = request.args.get("search", "").strip()

        with _conn() as conn:
            if search:
                rows = conn.execute(
                    """SELECT session_id, customer_name,
                              datetime(created_at,'unixepoch') as created,
                              datetime(updated_at,'unixepoch') as updated,
                              state_json, history_json
                       FROM conversation_sessions
                       WHERE session_id LIKE ? OR customer_name LIKE ?
                       ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
                    (f"%{search}%", f"%{search}%", limit, offset)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT session_id, customer_name,
                              datetime(created_at,'unixepoch') as created,
                              datetime(updated_at,'unixepoch') as updated,
                              state_json, history_json
                       FROM conversation_sessions
                       ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
                    (limit, offset)
                ).fetchall()

        sessions = []
        for r in rows:
            try:
                state = json.loads(r["state_json"])
                history = json.loads(r["history_json"])
            except Exception:
                state = {}
                history = []
            sessions.append({
                "session_id": r["session_id"],
                "customer_name": r["customer_name"],
                "created": r["created"],
                "updated": r["updated"],
                "category": state.get("category"),
                "stage": state.get("stage"),
                "turns": state.get("turns_count", len(history) // 2),
                "message_count": len(history),
                "requirements": state.get("requirements", {}),
            })

        return jsonify({"success": True, "sessions": sessions, "count": len(sessions)})
    except Exception as e:
        logger.error(f"Sessions list error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── API: Session Detail (full chat history) ──────────────────────────────────
@admin_bp.route("/api/admin/sessions/<session_id>")
def admin_session_detail(session_id: str):
    try:
        with _conn() as conn:
            row = conn.execute(
                """SELECT session_id, customer_name,
                          datetime(created_at,'unixepoch') as created,
                          datetime(updated_at,'unixepoch') as updated,
                          state_json, history_json
                   FROM conversation_sessions WHERE session_id = ?""",
                (session_id,)
            ).fetchone()

            if not row:
                return jsonify({"success": False, "error": "Session not found"}), 404

            leads = conn.execute(
                "SELECT * FROM commercial_leads WHERE session_id = ? ORDER BY created_at",
                (session_id,)
            ).fetchall()

        state = json.loads(row["state_json"])
        history = json.loads(row["history_json"])

        return jsonify({
            "success": True,
            "session_id": row["session_id"],
            "customer_name": row["customer_name"],
            "created": row["created"],
            "updated": row["updated"],
            "state": state,
            "history": history,
            "leads": [dict(l) for l in leads],
        })
    except Exception as e:
        logger.error(f"Session detail error {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── API: Leads List ──────────────────────────────────────────────────────────
@admin_bp.route("/api/admin/leads")
def admin_leads():
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        with _conn() as conn:
            rows = conn.execute(
                """SELECT lead_id, session_id,
                          datetime(created_at,'unixepoch') as created,
                          customer_name, company, email, phone, product_interest, notes
                   FROM commercial_leads ORDER BY created_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()
        return jsonify({"success": True, "leads": [dict(r) for r in rows], "count": len(rows)})
    except Exception as e:
        logger.error(f"Leads error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
