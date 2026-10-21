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


def send_sms(phone: str, message: str, *, timeout: float | None = None) -> dict[str, Any]:
    if not phone:
        return {"status": "skipped", "reason": "missing_phone_number"}

    if not is_twilio_configured():
        return {
            "status": "mocked",
            "message": message,
            "phone": phone,
            "note": "Twilio is not configured yet. This is a safe mock response for local testing.",
        }

    try:
        from twilio.http.http_client import TwilioHttpClient
        from twilio.rest import Client

        client_kwargs: dict[str, Any] = {}
        if timeout is not None:
            client_kwargs["http_client"] = TwilioHttpClient(timeout=timeout)
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token, **client_kwargs)
        sent = client.messages.create(body=message, from_=settings.twilio_from_number, to=phone)
        return {
            "status": "sent",
            "sid": sent.sid,
            "message": message,
            "phone": phone,
        }
    except Exception as exc:  # pragma: no cover - runtime integration dependency
        return {
            "status": "error",
            "error": str(exc),
            "message": message,
            "phone": phone,
        }
