from __future__ import annotations

from typing import Any

from app.config import settings


def is_twilio_configured() -> bool:
    return bool(settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number)


def build_missing_call_reply(lead: dict[str, Any]) -> str:
    service = (lead.get("service_type") or "HVAC service").title()
    return (
        f"Hi {lead.get('customer_name', 'there')}, thanks for contacting us about {service}. "
        "We’re here to help and can schedule a service visit. Reply with your address and best time window."
    )


def send_sms(phone: str, message: str) -> dict[str, Any]:
    # Explicitly draft-only until consent, transport and delivery reconciliation exist.
    return {"status": "draft", "message": message, "phone": phone,
            "note": "Not sent. Live messaging is disabled in this local pilot."}
