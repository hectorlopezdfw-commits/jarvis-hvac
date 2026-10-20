from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import FollowUpRequest, LeadBooking, LeadRequest, ReviewRequestPayload
from app.services.lead_service import (
    book_lead,
    create_lead,
    get_ai_qualification_preview,
    get_dashboard_summary,
    get_lead,
    get_sales_offer,
    get_sales_pitch,
    list_leads,
    request_review_for_lead,
    send_lead_follow_up,
)

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def dashboard() -> dict[str, Any]:
    return get_dashboard_summary()


@router.get("/leads")
def get_all_leads() -> list[dict[str, Any]]:
    return list_leads()


@router.get("/leads/{lead_id}")
def get_single_lead(lead_id: str) -> dict[str, Any]:
    lead = get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("/leads")
def submit_lead(payload: LeadRequest) -> dict[str, Any]:
    try:
        return create_lead(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/book")
def book(lead_id: str, payload: LeadBooking) -> dict[str, Any]:
    try:
        return book_lead(lead_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/follow-up")
def follow_up(lead_id: str, payload: FollowUpRequest) -> dict[str, Any]:
    try:
        return send_lead_follow_up(lead_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/review-request")
def review_request(lead_id: str, payload: ReviewRequestPayload) -> dict[str, Any]:
    try:
        return request_review_for_lead(lead_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ai/qualify")
def qualify_lead(payload: LeadRequest) -> dict[str, Any]:
    return get_ai_qualification_preview(payload)


@router.get("/sales-offer")
def sales_offer() -> dict[str, Any]:
    return get_sales_offer()


@router.get("/sales-pitch")
def sales_pitch() -> str:
    return get_sales_pitch()
