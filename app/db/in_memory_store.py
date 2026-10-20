"""Persistent, tenant-scoped successor to the original in-memory lead store."""
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

scope = ContextVar('lead_tenant', default=None)


def db_path():
    path = Path(os.environ.get('JARVIS_DB', str(Path(__file__).resolve().parents[2]/'data/jarvis.sqlite')))
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


class InMemoryLeadStore:
    # Retain the import/interface for compatibility with the existing application.
    @contextmanager
    def connect(self):
        connection = sqlite3.connect(db_path(), timeout=10)
        connection.execute('CREATE TABLE IF NOT EXISTS leads(tenant TEXT NOT NULL,id TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(tenant,id))')
        connection.execute('CREATE TABLE IF NOT EXISTS lead_audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,tenant TEXT NOT NULL,lead_id TEXT NOT NULL,kind TEXT NOT NULL,at TEXT NOT NULL)')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def tenant(self):
        tenant = scope.get()
        if not tenant:
            raise ValueError('Authenticated tenant required')
        return tenant

    def create(self, lead):
        tenant = self.tenant()
        record = dict(lead)
        record['id'] = 'lead-'+uuid4().hex[:16]
        record.setdefault('created_at', datetime.now(timezone.utc).isoformat())
        with self.connect() as connection:
            connection.execute('INSERT INTO leads VALUES(?,?,?)', (tenant,record['id'],json.dumps(record)))
            connection.execute('INSERT INTO lead_audit(tenant,lead_id,kind,at) VALUES(?,?,?,?)',(tenant,record['id'],'lead.created',record['created_at']))
        return record

    def list(self):
        with self.connect() as connection:
            return [json.loads(r[0]) for r in connection.execute('SELECT body FROM leads WHERE tenant=? ORDER BY rowid DESC',(self.tenant(),))]

    def get(self, lead_id):
        with self.connect() as connection:
            row = connection.execute('SELECT body FROM leads WHERE tenant=? AND id=?',(self.tenant(),lead_id)).fetchone()
            return json.loads(row[0]) if row else None

    def update(self, lead_id, updates):
        tenant = self.tenant()
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT body FROM leads WHERE tenant=? AND id=?',(tenant,lead_id)).fetchone()
            if row is None:
                raise KeyError('Lead not found')
            record = json.loads(row[0])
            record.update(updates)
            record['id'] = lead_id
            connection.execute('UPDATE leads SET body=? WHERE tenant=? AND id=?',(json.dumps(record),tenant,lead_id))
            connection.execute('INSERT INTO lead_audit(tenant,lead_id,kind,at) VALUES(?,?,?,?)',(tenant,lead_id,'lead.updated',datetime.now(timezone.utc).isoformat()))
        return record


lead_store = InMemoryLeadStore()
