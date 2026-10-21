from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import HTTPException, Request, Response

from app.config import settings

SESSION_COOKIE = "jarvis_session"
_SESSION_CONTEXT = b"jarvis-hvac-dashboard-v1"


def current_dashboard_password() -> str:
    raw = os.environ.get("DASHBOARD_PASSWORD", settings.dashboard_password)
    return (raw or "").strip()


def session_token(password: str) -> str:
    return hmac.new(password.encode("utf-8"), _SESSION_CONTEXT, hashlib.sha256).hexdigest()


def _secure_cookie() -> bool:
    return settings.app_env == "production"


def passwords_match(supplied: str, expected: str) -> bool:
    supplied_bytes = (supplied or "").encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    if len(supplied_bytes) != len(expected_bytes):
        return False
    return hmac.compare_digest(supplied_bytes, expected_bytes)


def is_request_authenticated(request: Request) -> bool:
    password = current_dashboard_password()
    if not password:
        return False
    expected = session_token(password)
    supplied = request.cookies.get(SESSION_COOKIE, "")
    if not supplied:
        return False
    return hmac.compare_digest(supplied, expected)


def require_dashboard_auth(request: Request) -> None:
    if is_request_authenticated(request):
        return
    if not current_dashboard_password():
        raise HTTPException(status_code=401, detail="Dashboard password is not configured")
    raise HTTPException(status_code=401, detail="Authentication required")


def apply_session_cookie(response: Response, token: str | None) -> None:
    if token is None:
        response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax", secure=_secure_cookie())
        return
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=_secure_cookie(),
        max_age=60 * 60 * 24 * 14,
        path="/",
    )
