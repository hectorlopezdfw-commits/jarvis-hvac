from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.db.store import SqlLeadStore
from app.main import app
from app.services.email import EMAIL_PROVIDERS, OutboundEmail, deliver_owner_email
from app.services.firstring import MAX_SIGNUP_BODY_BYTES, signup_alert_sms, signup_rate_limiter
from app.services.rate_limit import SlidingWindowRateLimiter

OWNER_PHONE = "+14695550100"
PROSPECT_PHONE_INPUT = "(214) 555-0199"
PROSPECT_PHONE = "+12145550199"


@pytest.fixture(autouse=True)
def _reset_signup_rate_limiter() -> None:
    signup_rate_limiter.reset()
    signup_rate_limiter.max_hits = 10
    signup_rate_limiter.window_seconds = 600


def _payload(**overrides: object) -> dict:
    data: dict = {
        "business_name": "Lopez HVAC",
        "contact_name": "Maria Lopez",
        "phone": PROSPECT_PHONE_INPUT,
        "email": "Maria@LopezHVAC.example",
        "trade": "HVAC",
        "service_area": "Dallas-Fort Worth",
        "team_size": "4",
        "monthly_calls": "about 80",
        "how_calls_answered_now": "Owner answers when he can",
        "needs": "Text back missed calls",
        "challenges": "Jobs slip through after hours",
        "plan_interest": "Growth",
        "best_time_to_call": "Weekdays after 4pm",
        "language": "es",
        "sms_consent": True,
        "website": "",
    }
    data.update(overrides)
    return data


def _login(client: TestClient) -> TestClient:
    response = client.post("/api/login", json={"password": "test-password"})
    assert response.status_code == 200
    return client


def _named(client: TestClient, business_name: str) -> list[dict]:
    response = client.get("/api/firstring/signups")
    assert response.status_code == 200
    return [row for row in response.json() if row["business_name"] == business_name]


def test_signup_stores_e164_and_list_requires_login() -> None:
    anonymous = TestClient(app)
    assert anonymous.get("/api/firstring/signups").status_code == 401

    created = anonymous.post("/api/firstring/signup", json=_payload())
    assert created.status_code == 200
    assert created.json() == {"ok": True}

    client = _login(TestClient(app))
    rows = _named(client, "Lopez HVAC")
    assert len(rows) == 1
    row = rows[0]
    assert row["id"].startswith("signup-")
    assert row["phone"] == PROSPECT_PHONE
    assert row["email"] == "maria@lopezhvac.example"
    assert row["trade"] == "HVAC"
    assert row["language"] == "es"
    assert row["plan_interest"] == "Growth"
    assert row["sms_consent"] is True
    assert row["needs"] == "Text back missed calls"
    assert row["challenges"] == "Jobs slip through after hours"
    assert "website" not in row
    assert row["notifications"]["sms"]["status"] == "skipped"
    assert row["notifications"]["email"]["status"] == "skipped"


def test_missing_and_invalid_fields_return_422() -> None:
    client = TestClient(app)
    missing = client.post("/api/firstring/signup", json={"contact_name": "Ada"})
    assert missing.status_code == 422
    locations = {tuple(error["loc"]) for error in missing.json()["detail"]}
    assert ("body", "business_name") in locations
    assert ("body", "phone") in locations
    assert ("body", "email") in locations
    assert ("body", "sms_consent") in locations

    invalid = client.post(
        "/api/firstring/signup",
        json=_payload(
            business_name="   ",
            phone="555-0111",
            email="not-an-email",
            plan_interest="Enterprise",
            language="fr",
            needs="x" * 4001,
        ),
    )
    assert invalid.status_code == 422
    invalid_locations = {tuple(error["loc"]) for error in invalid.json()["detail"]}
    assert ("body", "business_name") in invalid_locations
    assert ("body", "phone") in invalid_locations
    assert ("body", "email") in invalid_locations
    assert ("body", "plan_interest") in invalid_locations
    assert ("body", "language") in invalid_locations
    assert ("body", "needs") in invalid_locations

    broken = client.post(
        "/api/firstring/signup",
        content=b"{",
        headers={"Content-Type": "application/json"},
    )
    assert broken.status_code == 422
    assert client.post("/api/firstring/signup", content=b"", headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/api/firstring/signup", json=["not-an-object"]).status_code == 422


def test_optional_fields_can_be_omitted_and_language_is_normalized() -> None:
    client = TestClient(app)
    body = {
        "business_name": "Optional Plumbing",
        "contact_name": "Jon Ortiz",
        "phone": "1-214-555-0177",
        "email": "jon@example.com",
        "sms_consent": False,
        "language": "ES",
        "plan_interest": "Not sure",
        "trade": "   ",
    }
    assert client.post("/api/firstring/signup", json=body).status_code == 200
    client = _login(client)
    row = _named(client, "Optional Plumbing")[0]
    assert row["phone"] == "+12145550177"
    assert row["language"] == "es"
    assert row["plan_interest"] == "Not sure"
    assert row["trade"] is None
    assert row["needs"] is None
    assert row["sms_consent"] is False


def test_honeypot_returns_ok_and_is_not_stored(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(app)
    with caplog.at_level(logging.INFO):
        accepted = client.post(
            "/api/firstring/signup",
            json=_payload(business_name="Bot Plumbing", website="https://spam.example", email="not-an-email"),
        )
        blank = client.post(
            "/api/firstring/signup",
            json=_payload(business_name="Real Cleaning", website="   "),
        )
    assert accepted.status_code == 200
    assert accepted.json() == {"ok": True}
    assert blank.status_code == 200
    assert "honeypot" in caplog.text.lower()

    client = _login(client)
    names = {row["business_name"] for row in client.get("/api/firstring/signups").json()}
    assert "Bot Plumbing" not in names
    assert "Real Cleaning" in names


def test_rate_limit_is_per_ip() -> None:
    signup_rate_limiter.max_hits = 2
    client = TestClient(app)
    first_ip = {"X-Forwarded-For": "203.0.113.10, 10.0.0.1"}
    assert client.post("/api/firstring/signup", json=_payload(business_name="Rate One"), headers=first_ip).status_code == 200
    assert client.post("/api/firstring/signup", json=_payload(business_name="Rate Two"), headers=first_ip).status_code == 200
    blocked = client.post("/api/firstring/signup", json=_payload(business_name="Rate Three"), headers=first_ip)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "600"

    other = client.post(
        "/api/firstring/signup",
        json=_payload(business_name="Rate Other"),
        headers={"X-Forwarded-For": "203.0.113.11"},
    )
    assert other.status_code == 200

    client = _login(client)
    names = {row["business_name"] for row in client.get("/api/firstring/signups").json()}
    assert "Rate Three" not in names
    assert "Rate Other" in names
    stored = _named(client, "Rate One")[0]
    assert stored["source_ip"] == "203.0.113.10"


def test_rate_limiter_window_expires() -> None:
    limiter = SlidingWindowRateLimiter(max_hits=1, window_seconds=10)
    assert limiter.allow("203.0.113.8", now=100)
    assert limiter.allow("203.0.113.8", now=105) is False
    assert limiter.allow("203.0.113.9", now=105) is True
    assert limiter.allow("203.0.113.8", now=111) is True


def test_oversized_body_is_rejected() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/firstring/signup",
        content=b"{" + (b"x" * (MAX_SIGNUP_BODY_BYTES + 20)),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_cors_allows_only_firstring_origins() -> None:
    client = TestClient(app)
    for origin in ("https://firstringtx.com", "https://www.firstringtx.com"):
        preflight = client.options(
            "/api/firstring/signup",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin
        allowed_methods = preflight.headers["access-control-allow-methods"].upper()
        assert "POST" in allowed_methods
        assert "OPTIONS" in allowed_methods
        assert "content-type" in preflight.headers["access-control-allow-headers"].lower()

    blocked = client.options(
        "/api/firstring/signup",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert blocked.headers.get("access-control-allow-origin") != "https://evil.example"

    posted = client.post(
        "/api/firstring/signup",
        json=_payload(business_name="CORS HVAC"),
        headers={"Origin": "https://www.firstringtx.com"},
    )
    assert posted.status_code == 200
    assert posted.headers["access-control-allow-origin"] == "https://www.firstringtx.com"


def test_unconfigured_alerts_are_logged_and_skipped(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    for name in ("OWNER_ALERT_PHONE", "OWNER_ALERT_EMAIL", "RESEND_API_KEY", "ALERT_FROM_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    client = TestClient(app)
    with caplog.at_level(logging.INFO):
        response = client.post("/api/firstring/signup", json=_payload(business_name="Quiet Alerts"))
    assert response.status_code == 200
    assert "Skipping FirstRing sign-up SMS" in caplog.text
    assert "Skipping owner alert email" in caplog.text
    client = _login(client)
    notes = _named(client, "Quiet Alerts")[0]["notifications"]
    assert notes["sms"] == {"status": "skipped", "reason": "owner_alert_phone_not_configured"}
    assert notes["email"]["status"] == "skipped"
    assert notes["email"]["reason"] == "email_not_configured"


def test_sms_goes_to_owner_and_names_the_signup(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict = {}

    def fake_send(phone: str, message: str, *, timeout: float | None = None) -> dict:
        sent["phone"] = phone
        sent["message"] = message
        sent["timeout"] = timeout
        return {"status": "sent", "sid": "SM123"}

    monkeypatch.setenv("OWNER_ALERT_PHONE", "(469) 555-0100")
    monkeypatch.setattr("app.services.firstring.is_twilio_configured", lambda: True)
    monkeypatch.setattr("app.services.firstring.send_sms", fake_send)

    client = TestClient(app)
    response = client.post("/api/firstring/signup", json=_payload(business_name="SMS HVAC", plan_interest="Pro"))
    assert response.status_code == 200
    assert sent["phone"] == OWNER_PHONE
    assert sent["phone"] != PROSPECT_PHONE
    assert sent["timeout"] == 8.0
    message = sent["message"]
    assert message.startswith("New FirstRing sign-up:")
    assert "Maria Lopez" in message
    assert "SMS HVAC" in message
    assert "HVAC" in message
    assert PROSPECT_PHONE in message
    assert "Pro" in message

    client = _login(client)
    assert _named(client, "SMS HVAC")[0]["notifications"]["sms"] == {"status": "sent", "sid": "SM123"}


def test_email_posts_full_answers_to_resend(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Response:
        status_code = 200
        content = b'{"id":"email_123"}'
        text = '{"id":"email_123"}'

        def json(self) -> dict:
            return {"id": "email_123"}

    def fake_post(url: str, headers: dict | None = None, json: dict | None = None, timeout: float | None = None) -> _Response:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setenv("OWNER_ALERT_EMAIL", "owner@example.com")
    monkeypatch.setenv("ALERT_FROM_EMAIL", "alerts@firstringtx.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr("app.services.email.httpx.post", fake_post)

    client = TestClient(app)
    response = client.post("/api/firstring/signup", json=_payload(business_name="Email Roofing", trade="Roofing"))
    assert response.status_code == 200
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test_key"
    assert captured["timeout"] == 8.0
    body = captured["json"]
    assert body["from"] == "alerts@firstringtx.com"
    assert body["to"] == ["owner@example.com"]
    assert body["subject"] == "New FirstRing sign-up: Email Roofing"
    assert "Jobs slip through after hours" in body["text"]
    assert "Text back missed calls" in body["text"]
    assert PROSPECT_PHONE in body["text"]
    assert "Roofing" in body["text"]
    assert "re_test_key" not in body["text"]

    client = _login(client)
    assert _named(client, "Email Roofing")[0]["notifications"]["email"] == {"status": "sent", "id": "email_123"}


def test_alert_failures_still_store_the_signup(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        status_code = 503
        content = b"unavailable"
        text = "unavailable"

        def json(self) -> dict:
            return {}

    def explode(phone: str, message: str, *, timeout: float | None = None) -> dict:
        raise RuntimeError("twilio down")

    monkeypatch.setenv("OWNER_ALERT_PHONE", OWNER_PHONE)
    monkeypatch.setenv("OWNER_ALERT_EMAIL", "owner@example.com")
    monkeypatch.setenv("ALERT_FROM_EMAIL", "alerts@firstringtx.com")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setattr("app.services.firstring.is_twilio_configured", lambda: True)
    monkeypatch.setattr("app.services.firstring.send_sms", explode)
    monkeypatch.setattr("app.services.email.httpx.post", lambda *args, **kwargs: _Response())

    client = TestClient(app)
    response = client.post("/api/firstring/signup", json=_payload(business_name="Alert Fail Co"))
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    client = _login(client)
    notes = _named(client, "Alert Fail Co")[0]["notifications"]
    assert notes["sms"]["status"] == "error"
    assert notes["email"] == {"status": "error", "error": "resend_http_503"}
    assert "re_test_key" not in str(notes)


def test_email_provider_can_be_swapped(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict = {}

    def fake_sender(message: OutboundEmail) -> dict:
        sent["to"] = message.to
        sent["subject"] = message.subject
        return {"status": "sent", "id": "fake-1"}

    monkeypatch.setitem(EMAIL_PROVIDERS, "fake", fake_sender)
    monkeypatch.setenv("EMAIL_PROVIDER", "fake")
    result = deliver_owner_email(
        OutboundEmail(to="owner@example.com", subject="Hello", text="Full answers", from_address="alerts@example.com")
    )
    assert result == {"status": "sent", "id": "fake-1"}
    assert sent == {"to": "owner@example.com", "subject": "Hello"}

    monkeypatch.setenv("EMAIL_PROVIDER", "does-not-exist")
    skipped = deliver_owner_email(
        OutboundEmail(to="owner@example.com", subject="Hello", text="Full answers", from_address="alerts@example.com")
    )
    assert skipped["status"] == "skipped"
    assert skipped["reason"] == "unknown_email_provider"


def test_signup_sms_includes_the_required_facts() -> None:
    text = signup_alert_sms(
        {
            "contact_name": "Maria Lopez",
            "business_name": "Lopez HVAC",
            "trade": "Plumbing",
            "phone": PROSPECT_PHONE,
            "plan_interest": "Starter",
        }
    )
    assert "New FirstRing sign-up" in text
    assert "Maria Lopez" in text
    assert "Lopez HVAC" in text
    assert "Plumbing" in text
    assert PROSPECT_PHONE in text
    assert "Starter" in text


def test_signup_persists_in_sqlite_and_lists_newest_first(tmp_path) -> None:
    url = "sqlite:///" + (tmp_path / "signups.db").as_posix()
    first = SqlLeadStore(url)
    older = first.create_signup({"business_name": "Older", "created_at": "2026-10-21T12:00:00+00:00", "phone": PROSPECT_PHONE})
    newer = first.create_signup({"business_name": "Newer", "created_at": "2026-10-21T13:00:00+00:00", "phone": PROSPECT_PHONE})
    first.dispose()

    second = SqlLeadStore(url)
    listed = second.list_signups()
    assert [row["id"] for row in listed] == [newer["id"], older["id"]]
    assert second.get_signup(older["id"])["business_name"] == "Older"
    updated = second.update_signup(older["id"], {"notifications": {"sms": {"status": "sent"}}})
    assert updated["notifications"]["sms"]["status"] == "sent"
    second.dispose()

    third = SqlLeadStore(url)
    assert third.get_signup(older["id"])["notifications"]["sms"]["status"] == "sent"
    third.dispose()


def test_signups_list_is_newest_first() -> None:
    client = _login(TestClient(app))
    assert client.post("/api/firstring/signup", json=_payload(business_name="First In")).status_code == 200
    assert client.post("/api/firstring/signup", json=_payload(business_name="Second In")).status_code == 200
    names = [row["business_name"] for row in client.get("/api/firstring/signups").json()]
    assert names.index("Second In") < names.index("First In")
