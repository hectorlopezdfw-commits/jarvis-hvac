from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import LeadBooking, LeadRequest, settings
from app.db.in_memory_store import lead_store
from app.services.lead_qualifier import build_dashboard_payload, classify_lead, format_follow_up_text, normalize_phone


def create_lead(payload: LeadRequest) -> dict[str, Any]:
    lead_payload = payload.model_dump()
    lead_payload["customer_name"] = payload.customer_name.strip()
    lead_payload["phone"] = normalize_phone(payload.phone)
    lead_payload["source"] = payload.source or "website"
    lead_payload["created_at"] = datetime.now(timezone.utc).isoformat()
    classified = classify_lead(lead_payload)
    lead_payload.update(classified)
    lead_payload["follow_up_text"] = format_follow_up_text(lead_payload)
    return lead_store.create(lead_payload)


def list_leads() -> list[dict[str, Any]]:
    return lead_store.list()


def get_lead(lead_id: str) -> dict[str, Any] | None:
    return lead_store.get(lead_id)


def book_lead(lead_id: str, booking: LeadBooking) -> dict[str, Any]:
    lead = lead_store.get(lead_id)
    if not lead:
        raise KeyError(f"Lead {lead_id} not found")

    updated = {
        "status": "booked",
        "appointment_time": booking.appointment_time,
        "technician_name": booking.technician_name,
        "booking_notes": booking.notes,
        "priority_label": lead.get("priority_label", "medium"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return lead_store.update(lead_id, updated)


def get_dashboard_summary() -> dict[str, Any]:
    return build_dashboard_payload(list_leads())


def get_ai_qualification_preview(payload: LeadRequest) -> dict[str, Any]:
    lead_data = payload.model_dump()
    lead_data["phone"] = normalize_phone(payload.phone)
    lead_data["source"] = payload.source or "website"
    lead_data["created_at"] = datetime.now(timezone.utc).isoformat()
    classified = classify_lead(lead_data)
    lead_data.update(classified)
    lead_data["follow_up_text"] = format_follow_up_text(lead_data)
    return lead_data
