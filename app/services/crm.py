from __future__ import annotations

from typing import Any


def build_crm_summary(leads: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(leads)
    booked = sum(1 for lead in leads if str(lead.get("status")).lower() == "booked")
    emergency = sum(1 for lead in leads if lead.get("emergency"))
    critical = sum(1 for lead in leads if str(lead.get("priority_label")).lower() == "critical")
    return {
        "total_leads": total,
        "booked_leads": booked,
        "emergency_leads": emergency,
        "critical_leads": critical,
        "lead_sources": sorted({str(lead.get("source", "unknown")).lower() for lead in leads}),
    }
