from __future__ import annotations

from typing import Any

from app.config import settings


def build_review_request_message(lead: dict[str, Any]) -> str:
    customer_name = lead.get("customer_name", "there")
    return (
        f"Hi {customer_name}, thanks for choosing us for your HVAC service. We would really appreciate a quick review of your experience. "
        f"You can leave it here: {lead.get('review_link', settings.default_review_link)}"
    )


def create_review_link(lead: dict[str, Any], review_link: str | None = None) -> str:
    return review_link or settings.default_review_link


def send_review_request(lead: dict[str, Any], review_link: str | None = None) -> dict[str, Any]:
    final_link = create_review_link(lead, review_link)
    message = build_review_request_message({**lead, "review_link": final_link})
    return {
        "lead_id": lead.get("id"),
        "review_link": final_link,
        "message": message,
        "status": "ready",
    }
