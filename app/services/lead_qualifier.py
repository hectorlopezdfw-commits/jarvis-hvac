from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.config import settings


def normalize_service_type(service_type: str) -> str:
    return (service_type or "service").strip().lower()


def _priority_score(raw_service: str, property_type: str, emergency: bool, notes: str | None = None) -> int:
    score = 20
    service = normalize_service_type(raw_service)

    if service in {"emergency", "repair", "heating", "cooling", "furnace", "ac"}:
        score += 25
    if service in {"installation", "replacement", "system", "heat pump"}:
        score += 15
    if property_type == "commercial":
        score += 20
    if emergency:
        score += 30
    if notes and any(keyword in notes.lower() for keyword in ["no heat", "no cooling", "furnace", "outage", "broken", "urgent"]):
        score += 20
    return min(score, 100)


def priority_label(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def build_recommended_reply(lead: dict[str, Any]) -> str:
    service = lead.get("service_type", "HVAC service").title()
    property_type = lead.get("property_type", "residential")
    emergency = lead.get("emergency", False)

    if emergency:
        return (
            f"Thanks for reaching out. We can prioritize your {service} service for your {property_type} property. "
            "Reply with your address and preferred time window, and we’ll schedule the fastest available visit."
        )

    return (
        f"Thanks for contacting us about {service}. We can review your request and schedule a visit for your {property_type} property. "
        "Reply with your address and availability, and we’ll confirm the best time."
    )


def classify_lead(lead: dict[str, Any]) -> dict[str, Any]:
    service_type = normalize_service_type(lead.get("service_type", "service"))
    property_type = (lead.get("property_type") or "residential").strip().lower()
    emergency = bool(lead.get("emergency", False))
    notes = lead.get("notes") or ""

    score = _priority_score(service_type, property_type, emergency, notes)
    label = priority_label(score)

    payload = {
        "priority_score": score,
        "priority_label": label,
        "recommended_reply": build_recommended_reply(lead),
        "status": "new",
        "qualified": bool(score >= 40),
        "created_at": lead.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "service_type": service_type,
    }
    return payload


def build_dashboard_payload(leads: list[dict[str, Any]]) -> dict[str, Any]:
    total_leads = len(leads)
    booked_leads = sum(1 for lead in leads if lead.get("status") == "booked")
    emergency_leads = sum(1 for lead in leads if lead.get("emergency"))
    avg_priority = sum(int(lead.get("priority_score", 0)) for lead in leads) / total_leads if total_leads else 0
    open_leads = sum(1 for lead in leads if lead.get("status") in {"new", "contacted"})

    return {
        "total_leads": total_leads,
        "booked_leads": booked_leads,
        "emergency_leads": emergency_leads,
        "avg_priority": round(avg_priority, 2),
        "open_leads": open_leads,
    }


def normalize_phone(value: str | None) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D+", "", value)
    return digits


def format_follow_up_text(lead: dict[str, Any]) -> str:
    service = (lead.get("service_type") or "HVAC service").title()
    return (
        f"Hi {lead.get('customer_name', 'there')}, thanks for reaching out about {service}. We can help assess your HVAC issue. "
        "Reply with your address and best time window and we’ll follow up immediately."
    )
