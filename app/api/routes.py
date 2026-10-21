from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.auth import (
    apply_session_cookie,
    current_dashboard_password,
    is_request_authenticated,
    passwords_match,
    require_dashboard_auth,
    session_token,
)
from app.config import FollowUpRequest, LeadBooking, LeadRequest, LoginRequest, ReviewRequestPayload
from app.services.firstring import (
    MAX_SIGNUP_BODY_BYTES,
    SIGNUP_RATE_WINDOW_SECONDS,
    FirstRingSignupRequest,
    deliver_signup_alerts,
    honeypot_filled,
    ingest_firstring_signup,
    ingest_firstring_signup_honeypot,
    signup_rate_limiter,
    stored_signups,
)
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

_IP_TOKEN = re.compile(r"^[0-9A-Fa-f:.]+$")


def client_ip(request: Request) -> str:
    """First address in X-Forwarded-For (Render sends the visitor), else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    for part in forwarded.split(","):
        candidate = part.strip()
        if candidate and len(candidate) <= 64 and _IP_TOKEN.fullmatch(candidate):
            return candidate
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


async def limit_signup_body(request: Request) -> None:
    header = request.headers.get("content-length")
    if header:
        try:
            declared = int(header)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from None
        if declared > MAX_SIGNUP_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body is too large")
    body = await request.body()
    if len(body) > MAX_SIGNUP_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body is too large")


def limit_signup_rate(request: Request) -> None:
    if signup_rate_limiter.allow(client_ip(request)):
        return
    raise HTTPException(
        status_code=429,
        detail="Too many sign-up attempts. Try again later.",
        headers={"Retry-After": str(SIGNUP_RATE_WINDOW_SECONDS)},
    )


@router.post("/login")
def login(payload: LoginRequest) -> JSONResponse:
    password = current_dashboard_password()
    if not password:
        raise HTTPException(
            status_code=503,
            detail="Dashboard password is not configured. Set DASHBOARD_PASSWORD.",
        )
    if not passwords_match(payload.password, password):
        raise HTTPException(status_code=401, detail="Invalid password")
    response = JSONResponse({"ok": True})
    apply_session_cookie(response, session_token(password))
    return response


@router.post("/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    apply_session_cookie(response, None)
    return response


@router.get("/session")
def session_status(request: Request) -> dict[str, bool]:
    return {
        "configured": bool(current_dashboard_password()),
        "authenticated": is_request_authenticated(request),
    }


@router.get("/dashboard", dependencies=[Depends(require_dashboard_auth)])
def dashboard() -> dict[str, Any]:
    return get_dashboard_summary()


@router.get("/leads", dependencies=[Depends(require_dashboard_auth)])
def get_all_leads() -> list[dict[str, Any]]:
    return list_leads()


@router.get("/leads/{lead_id}", dependencies=[Depends(require_dashboard_auth)])
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


@router.post("/leads/{lead_id}/book", dependencies=[Depends(require_dashboard_auth)])
def book(lead_id: str, payload: LeadBooking) -> dict[str, Any]:
    try:
        return book_lead(lead_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/follow-up", dependencies=[Depends(require_dashboard_auth)])
def follow_up(lead_id: str, payload: FollowUpRequest) -> dict[str, Any]:
    try:
        return send_lead_follow_up(lead_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/review-request", dependencies=[Depends(require_dashboard_auth)])
def review_request(lead_id: str, payload: ReviewRequestPayload) -> dict[str, Any]:
    try:
        return request_review_for_lead(lead_id, payload)
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


def _signup_validation_error(exc: ValidationError) -> RequestValidationError:
    # Match FastAPI's body-parameter errors: loc starts with "body".
    errors = []
    for error in exc.errors():
        item = dict(error)
        item["loc"] = ("body", *item.get("loc", ()))
        errors.append(item)
    return RequestValidationError(errors)


@router.post(
    "/firstring/signup",
    dependencies=[Depends(limit_signup_body), Depends(limit_signup_rate)],
)
async def submit_firstring_signup(request: Request, background_tasks: BackgroundTasks) -> dict[str, bool]:
    """Store a FirstRing sign-up, then alert the owner.

    A non-empty `website` honeypot returns ok and is discarded, including when
    other fields are invalid, so a bot does not learn the validation rules.
    Alerts run after the response is written and cannot change this result.
    """
    raw = await request.body()
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError as exc:
        raise RequestValidationError(
            [
                {
                    "type": "json_invalid",
                    "loc": ("body",),
                    "msg": "JSON decode error",
                    "input": raw.decode("utf-8", errors="replace")[:200],
                }
            ]
        ) from exc
    if isinstance(parsed, dict) and honeypot_filled(parsed.get("website")):
        ingest_firstring_signup_honeypot()
        return {"ok": True}
    try:
        payload = FirstRingSignupRequest.model_validate(parsed)
    except ValidationError as exc:
        raise _signup_validation_error(exc) from exc
    signup_id = ingest_firstring_signup(payload, client_ip(request))
    background_tasks.add_task(deliver_signup_alerts, signup_id)
    return {"ok": True}


@router.get("/firstring/signups", dependencies=[Depends(require_dashboard_auth)])
def list_firstring_signups() -> list[dict[str, Any]]:
    return stored_signups()
