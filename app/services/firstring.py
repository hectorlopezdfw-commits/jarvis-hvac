"""Public FirstRing sign-up intake.

The marketing site posts here. The row is stored before any owner alert is sent.
SMS and email failures are recorded on the row and never change the HTTP result.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import runtime_setting, settings
from app.db.store import lead_store
from app.services.email import OutboundEmail, deliver_owner_email
from app.services.lead_qualifier import normalize_phone
from app.services.rate_limit import SlidingWindowRateLimiter
from app.services.sms import is_twilio_configured, send_sms

logger = logging.getLogger(__name__)

FIRSTRING_CORS_ORIGINS = (
    "https://firstringtx.com",
    "https://www.firstringtx.com",
)
MAX_SIGNUP_BODY_BYTES = 32 * 1024
SIGNUP_RATE_MAX_HITS = 10
SIGNUP_RATE_WINDOW_SECONDS = 10 * 60
PLAN_INTERESTS = ("Starter", "Growth", "Pro", "Not sure")
LANGUAGES = ("en", "es")
SMS_ALERT_TIMEOUT_SECONDS = 8.0

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+\Z")
_OPTIONAL_TEXT = (
    "trade",
    "service_area",
    "team_size",
    "monthly_calls",
    "how_calls_answered_now",
    "needs",
    "challenges",
    "plan_interest",
    "best_time_to_call",
    "language",
)

signup_rate_limiter = SlidingWindowRateLimiter(SIGNUP_RATE_MAX_HITS, SIGNUP_RATE_WINDOW_SECONDS)


def honeypot_filled(value: object) -> bool:
    """True when the honeypot has content. JSON false/null and blank text do not count."""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


class FirstRingSignupRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    business_name: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=40)
    email: str = Field(min_length=3, max_length=254)
    trade: str | None = Field(default=None, max_length=100)
    service_area: str | None = Field(default=None, max_length=200)
    team_size: str | None = Field(default=None, max_length=100)
    monthly_calls: str | None = Field(default=None, max_length=500)
    how_calls_answered_now: str | None = Field(default=None, max_length=500)
    needs: str | None = Field(default=None, max_length=4000)
    challenges: str | None = Field(default=None, max_length=4000)
    plan_interest: str | None = Field(default=None, max_length=40)
    best_time_to_call: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=8)
    sms_consent: bool
    website: str = ""

    @field_validator(*_OPTIONAL_TEXT, mode="before")
    @classmethod
    def blank_optional_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("website", mode="before")
    @classmethod
    def honeypot_text(cls, value: object) -> str:
        if not honeypot_filled(value):
            return ""
        return str(value).strip()

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        if _EMAIL.fullmatch(value) is None:
            raise ValueError("must be a valid email address")
        return value.lower()

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        normalized = normalize_phone(value)
        digits = re.sub(r"\D", "", normalized)
        if not normalized.startswith("+") or not 10 <= len(digits) <= 15:
            raise ValueError("must be a valid phone number")
        return normalized

    @field_validator("plan_interest")
    @classmethod
    def check_plan(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in PLAN_INTERESTS:
            raise ValueError("must be one of: Starter, Growth, Pro, Not sure")
        return value

    @field_validator("language")
    @classmethod
    def check_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        lowered = value.lower()
        if lowered not in LANGUAGES:
            raise ValueError("must be en or es")
        return lowered


def stored_signups() -> list[dict[str, Any]]:
    return lead_store.list_signups()


def ingest_firstring_signup_honeypot() -> None:
    logger.info("Dropped FirstRing sign-up because the honeypot field was filled")


def ingest_firstring_signup(payload: FirstRingSignupRequest, source_ip: str) -> str:
    """Persist the sign-up and return its id. Caller sends owner alerts afterward."""
    if payload.website:
        ingest_firstring_signup_honeypot()
        return ""
    stored = _store_signup(payload, source_ip)
    return str(stored["id"])


def deliver_signup_alerts(signup_id: str) -> None:
    """Send owner SMS and email, then record what happened. Never raises."""
    if not signup_id:
        return
    try:
        signup = lead_store.get_signup(signup_id)
        if signup is None:
            logger.error("FirstRing sign-up %s was missing before owner alerts ran", signup_id)
            return
        sms_status = _notify_sms(signup)
        email_status = _notify_email(signup)
        lead_store.update_signup(
            signup_id,
            {"notifications": {"sms": sms_status, "email": email_status}},
        )
    except Exception:
        logger.exception("Stored FirstRing sign-up %s but owner alerts failed", signup_id)


def signup_alert_sms(signup: dict[str, Any]) -> str:
    return (
        "New FirstRing sign-up: "
        f"{_clip(signup.get('contact_name'))}, {_clip(signup.get('business_name'))}. "
        f"Trade: {_clip(signup.get('trade'), 24)}. "
        f"Phone: {_clip(signup.get('phone'), 20)}. "
        f"Plan: {_clip(signup.get('plan_interest'), 24)}."
    )


def signup_alert_email(signup: dict[str, Any]) -> OutboundEmail:
    business = _clip(signup.get("business_name"), 80)
    if business == "n/a":
        business = "New business"
    lines = ["New FirstRing sign-up", ""]
    labels = (
        ("business_name", "Business"),
        ("contact_name", "Contact"),
        ("phone", "Phone"),
        ("email", "Email"),
        ("trade", "Trade"),
        ("service_area", "Service area"),
        ("team_size", "Team size"),
        ("monthly_calls", "Monthly calls"),
        ("how_calls_answered_now", "How calls are answered now"),
        ("needs", "Needs"),
        ("challenges", "Challenges"),
        ("plan_interest", "Plan interest"),
        ("best_time_to_call", "Best time to call"),
        ("language", "Language"),
        ("created_at", "Submitted at"),
        ("source_ip", "Source IP"),
        ("id", "Submission id"),
    )
    for key, label in labels:
        value = signup.get(key)
        text = "n/a" if value is None or value == "" else str(value)
        lines.append(f"{label}: {text}")
    lines.append(f"SMS consent: {'yes' if signup.get('sms_consent') else 'no'}")
    return OutboundEmail(
        to=runtime_setting("OWNER_ALERT_EMAIL", settings.owner_alert_email),
        from_address=runtime_setting("ALERT_FROM_EMAIL", settings.alert_from_email),
        subject=f"New FirstRing sign-up: {business}",
        text="\n".join(lines),
    )


def _store_signup(payload: FirstRingSignupRequest, source_ip: str) -> dict[str, Any]:
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "business_name": payload.business_name,
        "contact_name": payload.contact_name,
        "phone": payload.phone,
        "email": payload.email,
        "trade": payload.trade,
        "service_area": payload.service_area,
        "team_size": payload.team_size,
        "monthly_calls": payload.monthly_calls,
        "how_calls_answered_now": payload.how_calls_answered_now,
        "needs": payload.needs,
        "challenges": payload.challenges,
        "plan_interest": payload.plan_interest,
        "best_time_to_call": payload.best_time_to_call,
        "language": payload.language,
        "sms_consent": payload.sms_consent,
        "source_ip": source_ip,
        "notifications": {
            "sms": {"status": "pending"},
            "email": {"status": "pending"},
        },
    }
    stored = lead_store.create_signup(record)
    logger.info("Stored FirstRing sign-up %s", stored.get("id"))
    return stored


def _notify_sms(signup: dict[str, Any]) -> dict[str, Any]:
    try:
        phone = normalize_phone(runtime_setting("OWNER_ALERT_PHONE", settings.owner_alert_phone))
        digits = re.sub(r"\D", "", phone)
        if not phone.startswith("+") or not 10 <= len(digits) <= 15:
            if not phone:
                logger.info("Skipping FirstRing sign-up SMS; OWNER_ALERT_PHONE is not set")
                return {"status": "skipped", "reason": "owner_alert_phone_not_configured"}
            logger.info("Skipping FirstRing sign-up SMS; OWNER_ALERT_PHONE is not a valid phone number")
            return {"status": "skipped", "reason": "owner_alert_phone_invalid"}
        if not is_twilio_configured():
            logger.info("Skipping FirstRing sign-up SMS; Twilio is not configured")
            return {"status": "skipped", "reason": "twilio_not_configured"}
        result = send_sms(phone, signup_alert_sms(signup), timeout=SMS_ALERT_TIMEOUT_SECONDS)
        return _compact_status(result)
    except Exception as exc:
        logger.exception("FirstRing sign-up SMS failed")
        return {"status": "error", "error": type(exc).__name__}


def _notify_email(signup: dict[str, Any]) -> dict[str, Any]:
    try:
        result = deliver_owner_email(signup_alert_email(signup))
        return _compact_status(result, keep_missing=True)
    except Exception as exc:
        logger.exception("FirstRing sign-up email failed")
        return {"status": "error", "error": type(exc).__name__}


def _compact_status(result: dict[str, Any], *, keep_missing: bool = False) -> dict[str, Any]:
    compact: dict[str, Any] = {"status": str(result.get("status") or "error")}
    if result.get("reason"):
        compact["reason"] = str(result["reason"])[:120]
    if result.get("sid"):
        compact["sid"] = str(result["sid"])[:64]
    if result.get("id"):
        compact["id"] = str(result["id"])[:80]
    if result.get("error"):
        compact["error"] = str(result["error"])[:300]
    if keep_missing and result.get("missing"):
        compact["missing"] = [str(item)[:40] for item in result["missing"]]
    return compact


def _clip(value: object, limit: int = 48) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return "n/a"
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
