"""Owner-alert email over HTTP.

Resend is the built-in provider (Render's free tier blocks outbound SMTP).
To swap providers, register a function in EMAIL_PROVIDERS and set EMAIL_PROVIDER.
A sender receives an OutboundEmail and returns a status dict. It must not raise;
deliver_owner_email also catches anything that does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from app.config import runtime_setting, settings

logger = logging.getLogger(__name__)

RESEND_EMAILS_URL = "https://api.resend.com/emails"
EMAIL_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class OutboundEmail:
    to: str
    subject: str
    text: str
    from_address: str


EmailSender = Callable[[OutboundEmail], dict[str, Any]]


def deliver_owner_email(message: OutboundEmail) -> dict[str, Any]:
    provider_name = runtime_setting("EMAIL_PROVIDER", settings.email_provider).lower() or "resend"
    sender = EMAIL_PROVIDERS.get(provider_name)
    if sender is None:
        logger.error("Unknown EMAIL_PROVIDER %r; owner alert email skipped", provider_name)
        return {"status": "skipped", "reason": "unknown_email_provider"}
    try:
        return sender(message)
    except Exception as exc:
        logger.exception("Owner alert email failed")
        return {"status": "error", "error": type(exc).__name__}


def send_via_resend(message: OutboundEmail) -> dict[str, Any]:
    api_key = runtime_setting("RESEND_API_KEY", settings.resend_api_key)
    missing = [
        name
        for name, value in (
            ("RESEND_API_KEY", api_key),
            ("OWNER_ALERT_EMAIL", message.to),
            ("ALERT_FROM_EMAIL", message.from_address),
        )
        if not value
    ]
    if missing:
        logger.info("Skipping owner alert email; not configured: %s", ", ".join(missing))
        return {"status": "skipped", "reason": "email_not_configured", "missing": missing}

    response = httpx.post(
        RESEND_EMAILS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": message.from_address,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
        },
        timeout=EMAIL_TIMEOUT_SECONDS,
    )
    if response.status_code >= 400:
        logger.error("Resend owner alert failed with HTTP %s", response.status_code)
        return {"status": "error", "error": f"resend_http_{response.status_code}"}
    body: dict[str, Any] = {}
    if response.content:
        try:
            parsed = response.json()
        except ValueError:
            parsed = {}
        if isinstance(parsed, dict):
            body = parsed
    result: dict[str, Any] = {"status": "sent"}
    if body.get("id"):
        result["id"] = str(body["id"])[:80]
    return result


EMAIL_PROVIDERS: dict[str, EmailSender] = {
    "resend": send_via_resend,
}
