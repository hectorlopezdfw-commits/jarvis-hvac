from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import LeadBooking, LeadRequest
from app.services.lead_qualifier import create_lead, get_ai_qualification_preview, get_dashboard_summary, get_lead, list_leads, book_lead

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
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ai/qualify")
def qualify_lead(payload: LeadRequest) -> dict[str, Any]:
    return get_ai_qualification_preview(payload)
