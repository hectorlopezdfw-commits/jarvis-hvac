from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import FollowUpRequest, LeadBooking, LeadRequest, ReviewRequestPayload
from app.db.in_memory_store import lead_store
from app.services.crm import build_crm_summary
from app.services.follow_up import send_follow_up
from app.services.lead_qualifier import build_dashboard_payload, classify_lead, format_follow_up_text, normalize_phone
from app.services.review_requests import send_review_request
from app.services.sales import build_sales_offer, build_sales_pitch
from app.services.sms import build_missing_call_reply, send_sms


def create_lead(payload: LeadRequest) -> dict[str, Any]:
    lead_payload = payload.model_dump()
    lead_payload["customer_name"] = payload.customer_name.strip()
    lead_payload["phone"] = normalize_phone(payload.phone)
    lead_payload["source"] = payload.source or "website"
    lead_payload["created_at"] = datetime.now(timezone.utc).isoformat()
    classified = classify_lead(lead_payload)
    lead_payload.update(classified)
    lead_payload["follow_up_text"] = format_follow_up_text(lead_payload)

    if lead_payload.get("emergency"):
        lead_payload["sms_response"] = build_missing_call_reply(lead_payload)
    else:
        lead_payload["sms_response"] = lead_payload["recommended_reply"]

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
    leads = list_leads()
    summary = build_dashboard_payload(leads)
    summary["crm"] = build_crm_summary(leads)
    return summary


def get_ai_qualification_preview(payload: LeadRequest) -> dict[str, Any]:
    lead_data = payload.model_dump()
    lead_data["phone"] = normalize_phone(payload.phone)
    lead_data["source"] = payload.source or "website"
    lead_data["created_at"] = datetime.now(timezone.utc).isoformat()
    classified = classify_lead(lead_data)
    lead_data.update(classified)
    lead_data["follow_up_text"] = format_follow_up_text(lead_data)
    return lead_data


def send_lead_follow_up(lead_id: str, request: FollowUpRequest) -> dict[str, Any]:
    lead = lead_store.get(lead_id)
    if not lead:
        raise KeyError(f"Lead {lead_id} not found")

    step = int(lead.get("follow_up_step", 0))
    message = request.message or lead.get("follow_up_text") or "Thank you for your interest."
    result = send_sms(lead.get("phone", ""), message) if request.channel.lower() == "sms" else {"status": "email-only", "message": message}
    lead_store.update(lead_id, {"status": "contacted", "follow_up_step": step + 1, "last_follow_up": datetime.now(timezone.utc).isoformat()})
    return {"lead_id": lead_id, "step": step, "result": result}


def request_review_for_lead(lead_id: str, payload: ReviewRequestPayload) -> dict[str, Any]:
    lead = lead_store.get(lead_id)
    if not lead:
        raise KeyError(f"Lead {lead_id} not found")

    review_request = send_review_request(lead, payload.review_link)
    lead_store.update(lead_id, {"review_requested": True, "status": "review_requested"})
    return review_request


def get_sales_offer() -> dict[str, Any]:
    return build_sales_offer()


def get_sales_pitch() -> str:
    return build_sales_pitch()
