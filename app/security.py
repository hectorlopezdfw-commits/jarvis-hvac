"""Local pilot identity; a production identity provider remains a deployment gate."""
from contextlib import contextmanager
from app.controls import Store
from app.controls.access import Access
from app.db.in_memory_store import db_path, lead_store

STAFF = {'owner': 'owner', 'dispatcher': 'dispatcher', 'finance': 'finance',
         'reviewer': 'finance_reviewer', 'quality': 'quality_reviewer',
         'compliance': 'compliance_reviewer'}


@contextmanager
def services():
    store = Store(db_path())
    try:
        yield store, Access(store)
    finally:
        store.close()


def bootstrap():
    with lead_store.connect():
        pass
    with services() as (store, access):
        for actor, role in STAFF.items():
            existing = store.db.execute('SELECT 1 FROM memberships WHERE tenant=? AND actor=?',('pilot-local',actor)).fetchone()
            if not existing:
                access.provision('pilot-local', actor, role)
