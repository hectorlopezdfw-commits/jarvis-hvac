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


def company_schema(store):
    store.db.execute("""CREATE TABLE IF NOT EXISTS companies(
      id TEXT PRIMARY KEY,name TEXT NOT NULL,service_area TEXT NOT NULL,
      timezone TEXT NOT NULL,messaging_provider TEXT NOT NULL,calendar_provider TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,demo INTEGER NOT NULL DEFAULT 1)""")


def provision_staff(access,store,company_id):
    for actor,role in STAFF.items():
        if not store.db.execute('SELECT 1 FROM memberships WHERE tenant=? AND actor=?',(company_id,actor)).fetchone():
            access.provision(company_id,actor,role)


def bootstrap():
    with lead_store.connect():
        pass
    with services() as (store,access):
        company_schema(store)
        for cid,name,area in [('pilot-local','Demo · Cedar Air','DFW'),('demo-gulf','Demo · Gulf Coast Mechanical','Gulf Coast')]:
            store.db.execute('INSERT OR IGNORE INTO companies VALUES(?,?,?,?,?,?,1,1)',
                             (cid,name,area,'America/Chicago','undecided','undecided'))
            provision_staff(access,store,cid)
        if not store.db.execute('SELECT 1 FROM memberships WHERE tenant=? AND actor=?',('__platform__','platform-demo')).fetchone():
            access.provision('__platform__','platform-demo','platform_admin')
