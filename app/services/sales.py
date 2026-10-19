from __future__ import annotations

from typing import Any

from app.config import settings


def build_sales_offer() -> dict[str, Any]:
    return {
        "title": "AI HVAC Lead Response & Booking System",
        "description": "A conversion engine for HVAC companies that answers leads instantly, books jobs, follows up, and requests reviews.",
        "pricing": {
            "setup_fee": "$2,500-$5,000",
            "monthly_retainer": "$800-$1,500",
        },
        "includes": [
            "Instant lead response",
            "Missed-call text back",
            "AI lead qualification",
            "Appointment booking automation",
            "Follow-up sequences",
            "Review request automation",
            "Performance dashboard",
        ],
        "target_customers": [
            "Residential HVAC businesses",
            "Commercial HVAC contractors",
            "Service companies with inconsistent follow-up",
        ],
        "business_name": settings.business_name,
        "app_url": settings.app_url,
    }


def build_sales_pitch() -> str:
    return (
        "We help HVAC businesses turn missed calls, website leads, and text inquiries into booked jobs with AI-powered response, "
        "automatic follow-up, and review generation. The system responds instantly, qualifies the lead, and gets the service booked "
        "without the owner manually chasing every inquiry."
    )
