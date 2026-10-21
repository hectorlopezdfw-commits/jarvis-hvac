from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class Settings:
    app_name: str = "Jarvis HVAC"
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    default_service_area: str = "local"
    default_timezone: str = "America/Chicago"
    business_name: str = "Your HVAC Company"
    app_url: str = "http://localhost:8000"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    default_review_link: str = "https://www.google.com/maps"
    review_request_message: str = "Thanks for choosing us! If you have a minute, could you leave us a quick review?"
    database_url: str = ""
    dashboard_password: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    import os

    from dotenv import load_dotenv

    load_dotenv()

    return Settings(
        app_name=os.getenv("APP_NAME", "Jarvis HVAC"),
        app_env=os.getenv("APP_ENV", "development"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        default_service_area=os.getenv("DEFAULT_SERVICE_AREA", "local"),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "America/Chicago"),
        business_name=os.getenv("BUSINESS_NAME", "Your HVAC Company"),
        app_url=os.getenv("APP_URL", "http://localhost:8000"),
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        twilio_from_number=os.getenv("TWILIO_FROM_NUMBER", ""),
        default_review_link=os.getenv("DEFAULT_REVIEW_LINK", "https://www.google.com/maps"),
        review_request_message=os.getenv(
            "REVIEW_REQUEST_MESSAGE",
            "Thanks for choosing us! If you have a minute, could you leave us a quick review?",
        ),
        database_url=os.getenv("DATABASE_URL", ""),
        dashboard_password=os.getenv("DASHBOARD_PASSWORD", ""),
    )


settings = get_settings()


class LeadRequest(BaseModel):
    customer_name: str
    phone: str
    email: str | None = None
    service_type: str
    property_type: Literal["residential", "commercial"]
    emergency: bool = False
    address: str | None = None
    preferred_date: str | None = None
    source: str = "website"
    notes: str | None = None


class LeadBooking(BaseModel):
    appointment_time: str
    technician_name: str | None = None
    notes: str | None = None


class FollowUpRequest(BaseModel):
    channel: str = "sms"
    message: str | None = None


class ReviewRequestPayload(BaseModel):
    review_link: str | None = None
    message: str | None = None


class LoginRequest(BaseModel):
    password: str = ""


class LeadResponse(BaseModel):
    id: str
    status: str
    priority_score: int
    priority_label: str
    recommended_reply: str
    created_at: str


class DashboardSummary(BaseModel):
    total_leads: int
    booked_leads: int
    emergency_leads: int
    avg_priority: float
    open_leads: int
