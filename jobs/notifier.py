"""
Notification dispatcher for Kepler Tech SalesAI Offline Jobs.
Dispatches commercial lead briefs, QA alerts, and policy updates to external channels.
Guarantees:
- Channel support: Webhook (HTTP POST), SMTP (Email), and Local Log
- Exponential backoff retry logic (up to 3 attempts)
- Idempotency tracking by unique lead_id / event_id (never dispatches duplicates)
- Zero blocking on chat runtime (strictly offline / async)
"""

import os
import json
import time
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from pydantic import BaseModel, Field

from config import (
    OFFICIAL_SUPPORT_EMAIL,
    OFFICIAL_INFO_EMAIL,
)

logger = logging.getLogger("jobs.notifier")

DISPATCH_LOG_PATH = Path("data/dispatched_notifications.json")


class NotificationPayload(BaseModel):
    event_id: str
    channel: str = "webhook"  # "webhook", "email", "log"
    recipient: Optional[str] = None
    subject: str
    body: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class DispatchResult(BaseModel):
    event_id: str
    channel: str
    success: bool
    attempts: int
    error: Optional[str] = None
    dispatched_at: Optional[float] = None
    idempotent_skip: bool = False


class NotificationDispatcher:
    def __init__(
        self,
        webhook_url: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        default_email: Optional[str] = None,
        dispatch_log_path: Path = DISPATCH_LOG_PATH,
    ):
        self.webhook_url = webhook_url or os.getenv("LEAD_NOTIFICATION_WEBHOOK_URL")
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST")
        self.smtp_port = int(smtp_port or os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self.default_email = default_email or OFFICIAL_SUPPORT_EMAIL or "sales@keplertech.ae"
        self.dispatch_log_path = Path(dispatch_log_path)
        self.dispatch_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._dispatched_cache = self._load_dispatched_cache()

    def _load_dispatched_cache(self) -> Dict[str, float]:
        if self.dispatch_log_path.exists():
            try:
                with open(self.dispatch_log_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load dispatched log: {e}")
        return {}

    def _record_dispatched(self, event_id: str):
        self._dispatched_cache[event_id] = time.time()
        try:
            with open(self.dispatch_log_path, "w", encoding="utf-8") as f:
                json.dump(self._dispatched_cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist dispatched event {event_id}: {e}")

    def is_already_dispatched(self, event_id: str) -> bool:
        return event_id in self._dispatched_cache

    def dispatch(
        self,
        payload: NotificationPayload,
        max_retries: int = 3,
        initial_backoff: float = 0.5,
        force: bool = False,
    ) -> DispatchResult:
        """
        Dispatches payload with idempotency check and retry backoff.
        """
        if not force and self.is_already_dispatched(payload.event_id):
            logger.info(f"Skipping dispatch: event '{payload.event_id}' already sent (idempotent).")
            return DispatchResult(
                event_id=payload.event_id,
                channel=payload.channel,
                success=True,
                attempts=0,
                idempotent_skip=True,
                dispatched_at=self._dispatched_cache.get(payload.event_id),
            )

        channel = payload.channel.lower()
        attempts = 0
        last_error = None

        for attempt in range(1, max_retries + 1):
            attempts = attempt
            try:
                if channel == "webhook":
                    self._dispatch_webhook(payload)
                elif channel == "email":
                    self._dispatch_email(payload)
                elif channel == "log":
                    self._dispatch_log(payload)
                else:
                    # Default fallback: structured log
                    self._dispatch_log(payload)

                # Record success
                self._record_dispatched(payload.event_id)
                logger.info(f"Notification '{payload.event_id}' sent successfully via {channel} on attempt {attempt}.")
                return DispatchResult(
                    event_id=payload.event_id,
                    channel=channel,
                    success=True,
                    attempts=attempts,
                    dispatched_at=time.time(),
                )
            except Exception as err:
                last_error = str(err)
                logger.warning(f"Notification '{payload.event_id}' attempt {attempt} failed: {err}")
                if attempt < max_retries:
                    sleep_time = initial_backoff * (2 ** (attempt - 1))
                    time.sleep(sleep_time)

        return DispatchResult(
            event_id=payload.event_id,
            channel=channel,
            success=False,
            attempts=attempts,
            error=last_error,
        )

    def _dispatch_webhook(self, payload: NotificationPayload):
        target_url = self.webhook_url
        if not target_url:
            # Fallback to local log when webhook URL is not configured
            logger.info(f"[MOCK WEBHOOK] No webhook URL configured. Logging payload: {payload.subject}")
            self._dispatch_log(payload)
            return

        resp = requests.post(
            target_url,
            json=payload.model_dump(),
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()

    def _dispatch_email(self, payload: NotificationPayload):
        recipient = payload.recipient or self.default_email
        if not self.smtp_host:
            logger.info(f"[MOCK SMTP] No SMTP server configured. Logging email to {recipient}: {payload.subject}")
            self._dispatch_log(payload)
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = payload.subject
        msg["From"] = self.smtp_user or "no-reply@keplertech.ae"
        msg["To"] = recipient

        part = MIMEText(payload.body, "plain", "utf-8")
        msg.attach(part)

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10.0) as server:
            server.starttls()
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            server.sendmail(msg["From"], [recipient], msg.as_string())

    def _dispatch_log(self, payload: NotificationPayload):
        log_file = Path("data/notifications.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{payload.channel.upper()}] {payload.subject}\n")
            f.write(f"Event ID: {payload.event_id}\n")
            f.write(f"Recipient: {payload.recipient}\n")
            f.write(f"Body: {payload.body}\n")
            f.write(f"Metadata: {json.dumps(payload.metadata)}\n")
            f.write("-" * 60 + "\n")
