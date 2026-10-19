from __future__ import annotations

from typing import Any

from app.services.sms import send_sms


def generate_follow_up_sequence(lead: dict[str, Any]) -> list[str]:
    service = (lead.get("service_type") or "HVAC service").title()
    return [
        f"Hi {lead.get('customer_name', 'there')}, thanks for reaching out about {service}. We can help schedule a service visit. Reply with your address and best time window.",
        f"Hi {lead.get('customer_name', 'there')}, we are still available to help with your HVAC issue. Let us know the problem and your preferred time and we will follow up quickly.",
        f"Hi {lead.get('customer_name', 'there')}, we want to make sure you got the help you need. If you are still looking for {service.lower()} service, reply here and we will help schedule it.",
    ]


def send_follow_up(lead: dict[str, Any], step: int = 0) -> dict[str, Any]:
    sequence = generate_follow_up_sequence(lead)
    message = sequence[min(step, len(sequence) - 1)]
    result = send_sms(lead.get("phone", ""), message)
    return {
        "lead_id": lead.get("id"),
        "step": step,
        "message": message,
        **result,
    }
