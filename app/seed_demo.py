"""Explicit synthetic starter records; never sends messages or calls AI."""
from datetime import datetime, timezone, timedelta
from app.security import bootstrap
from app.db.in_memory_store import scope, lead_store
from app.config import LeadRequest, LeadBooking
from app.services.lead_service import create_lead, book_lead


def main():
    bootstrap()
    token=scope.set('pilot-local')
    try:
        if lead_store.list():
            print('Workspace already has records; no synthetic records added.')
            return
        for name,service,kind,source,notes in [
            ('Demo · Residential inquiry','cooling','residential','missed_call','Synthetic AC repair inquiry; prefers afternoon.'),
            ('Demo · Commercial site','maintenance','commercial','website','Synthetic scheduled maintenance request.'),
            ('Demo · Replacement quote','installation','residential','text','Synthetic replacement estimate inquiry.')]:
            lead=create_lead(LeadRequest(customer_name=name,phone='2145550100',service_type=service,property_type=kind,source=source,notes=notes))
            if kind=='commercial':
                book_lead(lead['id'],LeadBooking(appointment_time=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()))
        print('Added three clearly labeled synthetic inquiries. No messages sent.')
    finally:
        scope.reset(token)


if __name__=='__main__':
    main()
