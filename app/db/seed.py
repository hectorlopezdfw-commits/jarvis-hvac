from __future__ import annotations

from typing import Any

from app.services.lead_qualifier import classify_lead, format_follow_up_text, normalize_phone
from app.services.sms import build_missing_call_reply

# Stable ids keep seeding idempotent. Phones are fictional 555 numbers.
SAMPLE_LEADS: list[dict[str, Any]] = [
    {
        "id": "seed-0001",
        "customer_name": "Maria Gonzalez",
        "phone": "2145550101",
        "email": "maria.gonzalez@example.com",
        "service_type": "heating",
        "property_type": "residential",
        "emergency": True,
        "address": "1842 S Beckley Ave, Dallas, TX 75224",
        "preferred_date": "2026-10-18T08:00:00",
        "source": "call",
        "notes": "No heat in the house overnight. Sample lead.",
        "created_at": "2026-10-18T13:05:00+00:00",
        "status": "new",
    },
    {
        "id": "seed-0002",
        "customer_name": "James Whitfield",
        "phone": "(214) 555-0102",
        "email": "james.whitfield@example.com",
        "service_type": "ac",
        "property_type": "residential",
        "emergency": True,
        "address": "6125 Lakewood Blvd, Dallas, TX 75214",
        "preferred_date": "2026-10-18T11:30:00",
        "source": "website",
        "notes": "No cooling on the second floor. Sample lead.",
        "created_at": "2026-10-18T15:40:00+00:00",
        "status": "booked",
        "appointment_time": "2026-10-18T18:00:00",
        "technician_name": "Andre Cole",
        "booking_notes": "Evening emergency window. Sample booking.",
        "updated_at": "2026-10-18T16:05:00+00:00",
    },
    {
        "id": "seed-0003",
        "customer_name": "Priya Shah",
        "phone": "9725550103",
        "email": "priya.shah@example.com",
        "service_type": "installation",
        "property_type": "commercial",
        "emergency": False,
        "address": "2200 Ross Ave, Dallas, TX 75201",
        "preferred_date": "2026-10-21T09:00:00",
        "source": "google",
        "notes": "Office buildout needs a new rooftop unit. Sample lead.",
        "created_at": "2026-10-19T14:10:00+00:00",
        "status": "new",
    },
    {
        "id": "seed-0004",
        "customer_name": "Derek Lang",
        "phone": "1-214-555-0104",
        "email": "derek.lang@example.com",
        "service_type": "furnace",
        "property_type": "commercial",
        "emergency": True,
        "address": "4100 W Airport Fwy, Irving, TX 75062",
        "preferred_date": "2026-10-19T07:00:00",
        "source": "call",
        "notes": "Warehouse furnace outage before the morning shift. Sample lead.",
        "created_at": "2026-10-19T12:20:00+00:00",
        "status": "booked",
        "appointment_time": "2026-10-19T13:30:00",
        "technician_name": "Riley Nguyen",
        "booking_notes": "Meet the facility manager at the dock. Sample booking.",
        "updated_at": "2026-10-19T12:35:00+00:00",
    },
    {
        "id": "seed-0005",
        "customer_name": "Alicia Nguyen",
        "phone": "4695550105",
        "email": "alicia.nguyen@example.com",
        "service_type": "maintenance",
        "property_type": "residential",
        "emergency": False,
        "address": "1501 K Ave, Plano, TX 75074",
        "preferred_date": "2026-10-22T10:00:00",
        "source": "text",
        "notes": "Seasonal tune-up before the first cold snap. Sample lead.",
        "created_at": "2026-10-19T18:00:00+00:00",
        "status": "contacted",
        "follow_up_step": 1,
        "last_follow_up": "2026-10-19T19:15:00+00:00",
    },
    {
        "id": "seed-0006",
        "customer_name": "Robert Hale",
        "phone": "2145550106",
        "email": "robert.hale@example.com",
        "service_type": "cooling",
        "property_type": "residential",
        "emergency": False,
        "address": "100 S Central Expy, Richardson, TX 75080",
        "preferred_date": "2026-10-20T15:00:00",
        "source": "website",
        "notes": "Upstairs runs warm in the afternoon. Sample lead.",
        "created_at": "2026-10-20T13:25:00+00:00",
        "status": "booked",
        "appointment_time": "2026-10-21T09:30:00",
        "technician_name": "Andre Cole",
        "booking_notes": "Homeowner works from home. Sample booking.",
        "updated_at": "2026-10-20T14:00:00+00:00",
    },
    {
        "id": "seed-0007",
        "customer_name": "Linda Cho",
        "phone": "+1 214 555 0107",
        "email": "linda.cho@example.com",
        "service_type": "ac",
        "property_type": "commercial",
        "emergency": True,
        "address": "8687 N Central Expy, Dallas, TX 75225",
        "preferred_date": "2026-10-20T08:30:00",
        "source": "call",
        "notes": "Clinic waiting room has no cooling. Sample lead.",
        "created_at": "2026-10-20T14:45:00+00:00",
        "status": "booked",
        "appointment_time": "2026-10-20T16:00:00",
        "technician_name": "Sam Ortiz",
        "booking_notes": "Check in at the front desk. Sample booking.",
        "updated_at": "2026-10-20T15:00:00+00:00",
    },
    {
        "id": "seed-0008",
        "customer_name": "Marcus Bennett",
        "phone": "9725550108",
        "email": "marcus.bennett@example.com",
        "service_type": "repair",
        "property_type": "commercial",
        "emergency": False,
        "address": "3100 Main St, Dallas, TX 75226",
        "preferred_date": "2026-10-23T12:00:00",
        "source": "google",
        "notes": "Restaurant rooftop unit is short cycling. Sample lead.",
        "created_at": "2026-10-20T20:10:00+00:00",
        "status": "new",
    },
    {
        "id": "seed-0009",
        "customer_name": "Sofia Ramirez",
        "phone": "4695550109",
        "email": "sofia.ramirez@example.com",
        "service_type": "furnace",
        "property_type": "residential",
        "emergency": True,
        "address": "3900 Cedar Springs Rd, Dallas, TX 75219",
        "preferred_date": "2026-10-21T07:30:00",
        "source": "call",
        "notes": "Furnace outage and the house is getting cold. Sample lead.",
        "created_at": "2026-10-21T12:05:00+00:00",
        "status": "new",
    },
    {
        "id": "seed-0010",
        "customer_name": "Helen Brooks",
        "phone": "2145550110",
        "email": "helen.brooks@example.com",
        "service_type": "maintenance",
        "property_type": "residential",
        "emergency": False,
        "address": "6423 Walnut Hill Ln, Dallas, TX 75230",
        "preferred_date": "2026-10-15T13:00:00",
        "source": "website",
        "notes": "Filter plan visit already completed. Sample lead.",
        "created_at": "2026-10-15T17:30:00+00:00",
        "status": "review_requested",
        "review_requested": True,
        "appointment_time": "2026-10-16T10:00:00",
        "technician_name": "Riley Nguyen",
        "updated_at": "2026-10-16T18:00:00+00:00",
    },
]


def build_seed_leads() -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for raw in SAMPLE_LEADS:
        payload = dict(raw)
        payload["customer_name"] = str(payload["customer_name"]).strip()
        payload["phone"] = normalize_phone(str(payload["phone"]))
        payload["source"] = payload.get("source") or "website"
        payload["created_at"] = raw["created_at"]
        classified = classify_lead(payload)
        payload.update(classified)
        payload["id"] = raw["id"]
        payload["created_at"] = raw["created_at"]
        payload["status"] = raw.get("status") or "new"
        payload["follow_up_text"] = format_follow_up_text(payload)
        if payload.get("emergency"):
            payload["sms_response"] = build_missing_call_reply(payload)
        else:
            payload["sms_response"] = payload["recommended_reply"]
        prepared.append(payload)
    return prepared


def seed_leads(store: Any) -> int:
    """Insert sample leads whose ids are not already stored. Safe to call on every startup."""
    inserted = 0
    for lead in build_seed_leads():
        if store.get(lead["id"]) is None:
            store.create(lead)
            inserted += 1
    return inserted
