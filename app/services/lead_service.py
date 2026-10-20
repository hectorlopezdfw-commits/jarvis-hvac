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
    if not lead_payload["customer_name"] or len(lead_payload["phone"]) < 7:
        raise ValueError("Customer name and valid phone digits required")
    lead_payload["source"] = payload.source or "website"
    lead_payload["created_at"] = datetime.now(timezone.utc).isoformat()
    classified = classify_lead(lead_payload)
    lead_payload.update(classified)
    lead_payload["follow_up_text"] = format_follow_up_text(lead_payload)

    if lead_payload.get("safety_hold"):
        lead_payload["sms_response"] = lead_payload["recommended_reply"]
    elif lead_payload.get("emergency"):
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

    if lead.get("safety_hold"):
        raise ValueError("Human safety review required; routine booking blocked")
    if lead.get("status") in {"completed", "lost", "booking_confirmed_simulated"}:
        raise ValueError("Closed lead cannot be booked")
    from datetime import datetime
    proposed = datetime.fromisoformat(booking.appointment_time.replace("Z", "+00:00"))
    if proposed.tzinfo is None or proposed <= datetime.now(timezone.utc):
        raise ValueError("Future appointment with timezone required")
    updated = {
        "status": "booking_requested",
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

    if lead.get("safety_hold"):
        raise ValueError("Routine follow-up blocked for safety review")
    step = int(lead.get("follow_up_step", 0))
    message = request.message or lead.get("follow_up_text") or "Thank you for your interest."
    # Drafting does not establish customer contact or advance the lifecycle.
    result = send_sms(lead.get("phone", ""), message)
    lead_store.update(lead_id, {"follow_up_draft": message})
    return {"lead_id": lead_id, "step": step, "result": result}


def request_review_for_lead(lead_id: str, payload: ReviewRequestPayload) -> dict[str, Any]:
    lead = lead_store.get(lead_id)
    if not lead:
        raise KeyError(f"Lead {lead_id} not found")

    if lead.get("status") != "completed":
        raise ValueError("Service completion required before review request")
    review_request = send_review_request(lead, payload.review_link)
    lead_store.update(lead_id, {"review_request_draft": review_request["message"]})
    return review_request


def get_sales_offer() -> dict[str, Any]:
    return build_sales_offer()


def get_sales_pitch() -> str:
    return build_sales_pitch()
