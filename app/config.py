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
