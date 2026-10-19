from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import LeadRequest


class InMemoryLeadStore:
    def __init__(self) -> None:
        self._leads: dict[str, dict[str, Any]] = {}

    def create(self, lead: dict[str, Any]) -> dict[str, Any]:
        lead_id = lead.get("id") or f"lead-{len(self._leads) + 1:04d}"
        lead["id"] = lead_id
        if "created_at" not in lead:
            lead["created_at"] = datetime.now(timezone.utc).isoformat()
        if "status" not in lead:
            lead["status"] = "new"
        if "priority_score" not in lead:
            lead["priority_score"] = 0
        if "priority_label" not in lead:
            lead["priority_label"] = "medium"
        self._leads[lead_id] = lead
        return dict(self._leads[lead_id])

    def list(self) -> list[dict[str, Any]]:
        return [dict(lead) for lead in self._leads.values()]

    def get(self, lead_id: str) -> dict[str, Any] | None:
        lead = self._leads.get(lead_id)
        return dict(lead) if lead else None

    def update(self, lead_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        if lead_id not in self._leads:
            raise KeyError(f"Lead {lead_id} not found")
        self._leads[lead_id].update(updates)
        return dict(self._leads[lead_id])


lead_store = InMemoryLeadStore()
