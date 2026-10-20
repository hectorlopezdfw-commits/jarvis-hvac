"""Add fictional records to two isolated client workspaces; no external calls."""
from datetime import datetime, timezone, timedelta
from app.security import bootstrap
from app.db.in_memory_store import scope, lead_store
from app.config import LeadRequest, LeadBooking
from app.services.lead_service import create_lead, book_lead


def main():
    bootstrap()
    added=0
    for company in ('pilot-local','demo-gulf'):
        token=scope.set(company)
        try:
            if lead_store.list():
                continue
            prefix='Demo · Cedar' if company=='pilot-local' else 'Demo · Gulf'
            for suffix,service,kind,source,notes in [
                (' residential inquiry','cooling','residential','missed_call','Synthetic AC repair inquiry.'),
                (' commercial site','maintenance','commercial','website','Synthetic maintenance request.')]:
                lead=create_lead(LeadRequest(customer_name=prefix+suffix,phone='2145550100',service_type=service,property_type=kind,source=source,notes=notes))
                if kind=='commercial':
                    book_lead(lead['id'],LeadBooking(appointment_time=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()))
                added+=1
        finally:
            scope.reset(token)
    print(f'Added {added} synthetic inquiries across empty demo company workspaces. No messages sent.')


if __name__=='__main__':
    main()
