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


# ── API: Live Sales Desk (Human Agent Takeover & Chat Console) ────────────────

@admin_bp.route("/api/admin/live-desk/sessions", methods=["GET"])
def live_desk_sessions():
    """Returns active chat sessions prioritized for live sales agent monitoring."""
    from domain.state_store import state_manager
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        filter_type = request.args.get("filter", "all")  # all | attention | agent | ai

        with _conn() as conn:
            rows = conn.execute(
                """SELECT session_id, customer_name,
                          datetime(created_at,'unixepoch') as created,
                          datetime(updated_at,'unixepoch') as updated,
                          updated_at as updated_ts,
                          state_json, history_json
                   FROM conversation_sessions
                   ORDER BY updated_at DESC LIMIT ?""",
                (limit,)
            ).fetchall()

        queue = []
        for r in rows:
            sid = r["session_id"]
            try:
                state_dict = json.loads(r["state_json"])
                history = json.loads(r["history_json"])
            except Exception:
                state_dict = {}
                history = []

            # Check in-memory state for immediate updates
            mem_state = state_manager.get(sid)
            if mem_state:
                state_dict = mem_state.to_dict()
                history = state_manager.get_history(sid)

            human_active = bool(state_dict.get("human_agent_active", False))
            handover_trig = bool(state_dict.get("handover_triggered", False))
            frustration = int(state_dict.get("frustration_count", 0))

            # Determine priority & tags
            needs_attention = handover_trig or frustration >= 2
            if human_active:
                status = "agent"
                priority = 2
            elif needs_attention:
                status = "attention"
                priority = 1
            else:
                status = "ai"
                priority = 3

            # Apply filter
            if filter_type == "attention" and not needs_attention:
                continue
            if filter_type == "agent" and not human_active:
                continue
            if filter_type == "ai" and (human_active or needs_attention):
                continue

            last_msg = ""
            last_sender = "unknown"
            if history:
                last_entry = history[-1]
                last_msg = last_entry.get("content") or last_entry.get("reply") or ""
                last_sender = last_entry.get("sender") or last_entry.get("role") or "unknown"

            queue.append({
                "session_id": sid,
                "customer_name": r["customer_name"] or state_dict.get("customer_name") or "Anonymous Visitor",
                "category": state_dict.get("category"),
                "stage": state_dict.get("stage", "open"),
                "status": status,
                "priority": priority,
                "human_agent_active": human_active,
                "human_agent_name": state_dict.get("human_agent_name"),
                "handover_triggered": handover_trig,
                "handover_reason": state_dict.get("handover_reason"),
                "frustration_count": frustration,
                "last_message": last_msg[:120],
                "last_sender": last_sender,
                "turns": len(history),
                "updated": r["updated"],
                "active_product": state_dict.get("active_product_id") or (state_dict.get("active_product") or {}).get("display_name"),
            })

        # Sort by priority (1=attention, 2=agent, 3=ai) then most recent
        queue.sort(key=lambda x: (x["priority"], -(time.time())))

        return jsonify({
            "success": True,
            "count": len(queue),
            "sessions": queue,
            "attention_count": sum(1 for q in queue if q["priority"] == 1),
            "agent_count": sum(1 for q in queue if q["human_agent_active"]),
        })
    except Exception as e:
        logger.error(f"Live desk sessions error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/admin/live-desk/takeover", methods=["POST"])
def live_desk_takeover():
    """Agent takes control of chat session — pauses SalesAI automated bot replies."""
    from domain.state_store import state_manager
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    agent_name = data.get("agent_name") or "Sales Specialist"
    reason = data.get("reason") or "manual_takeover"

    if not session_id:
        return jsonify({"success": False, "error": "Missing session_id"}), 400

    try:
        state = state_manager.set_agent_takeover(
            session_id=session_id,
            agent_name=agent_name,
            reason=reason
        )
        return jsonify({
            "success": True,
            "message": f"Session taken over by {agent_name}. AI replies paused.",
            "state": state.to_dict(),
        })
    except Exception as e:
        logger.error(f"Takeover error {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/admin/live-desk/release", methods=["POST"])
def live_desk_release():
    """Agent releases chat session back to automated SalesAI assistant."""
    from domain.state_store import state_manager
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"success": False, "error": "Missing session_id"}), 400

    try:
        state = state_manager.release_agent_takeover(session_id=session_id)
        return jsonify({
            "success": True,
            "message": "Session released back to SalesAI automated assistance.",
            "state": state.to_dict(),
        })
    except Exception as e:
        logger.error(f"Release error {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/admin/live-desk/send", methods=["POST"])
def live_desk_send():
    """Sales agent sends a manual message to the customer's chat session."""
    from domain.state_store import state_manager
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    message = data.get("message", "").strip()
    agent_name = data.get("agent_name") or "Sales Specialist"

    if not session_id or not message:
        return jsonify({"success": False, "error": "session_id and message are required"}), 400

    try:
        msg_obj = state_manager.add_agent_message(
            session_id=session_id,
            message=message,
            agent_name=agent_name
        )
        return jsonify({
            "success": True,
            "sent_message": msg_obj,
        })
    except Exception as e:
        logger.error(f"Agent send error {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@admin_bp.route("/api/admin/live-desk/poll", methods=["GET"])
def live_desk_poll():
    """Polls real-time messages and state for the active session in the admin console."""
    from domain.state_store import state_manager
    session_id = request.args.get("session_id")
    last_count = int(request.args.get("last_count", 0))

    if not session_id:
        return jsonify({"success": False, "error": "Missing session_id"}), 400

    try:
        poll_data = state_manager.get_poll_data(session_id=session_id, last_count=last_count)
        state = state_manager.get_or_create(session_id)

        # Build Copilot Suggestion
        copilot_draft = None
        act_prod = state.active_product
        if act_prod:
            name = act_prod.get("display_name") or act_prod.get("name")
            copilot_draft = f"I'd be glad to arrange a tailored quotation and technical demonstration for the {name}. Would you like me to send full specifications to your email?"
        elif state.requirements.get("paper_size"):
            ps = str(state.requirements.get("paper_size")).upper()
            copilot_draft = f"For your {ps} requirement, our top recommendation from the approved Kepler Tech catalogue is ready for review. What is your estimated monthly volume?"

        poll_data["copilot_draft"] = copilot_draft
        poll_data["state"] = state.to_dict()
        poll_data["success"] = True
        return jsonify(poll_data)
    except Exception as e:
        logger.error(f"Live desk poll error {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

