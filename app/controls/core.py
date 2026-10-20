"""Application controls for a synthetic HVAC pilot; no external writes or AI calls."""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import json
import sqlite3
from uuid import uuid4


class WorkflowError(ValueError):
    pass


@dataclass(frozen=True)
class Context:
    # Supplied by a trusted application boundary, never by customer text.
    tenant: str
    actor: str
    role: str


def now():
    return datetime.now(timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def money(value):
    if type(value) is not int or value < 0:
        raise WorkflowError('Money must be nonnegative integer USD cents')
    return value


class Store:
    """SQLite pilot store. Public methods require a trusted Context.

    This is an application library, not an authentication provider. SQLite files
    must be private to the service; SQL access bypasses these application controls.
    """
    def __init__(self, path=':memory:'):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs (
          tenant TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL,
          state TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT '[]',
          PRIMARY KEY(tenant,id));
        CREATE TABLE IF NOT EXISTS holds (
          tenant TEXT NOT NULL, job TEXT NOT NULL, kind TEXT NOT NULL,
          reason TEXT NOT NULL, active INTEGER NOT NULL,
          PRIMARY KEY(tenant,job,kind),
          FOREIGN KEY(tenant,job) REFERENCES jobs(tenant,id));
        CREATE TABLE IF NOT EXISTS proposals (
          tenant TEXT NOT NULL, id TEXT NOT NULL, job TEXT NOT NULL,
          version INTEGER NOT NULL, requester TEXT NOT NULL,
          body TEXT NOT NULL, hash TEXT NOT NULL, expires TEXT NOT NULL,
          approver TEXT, approved_hash TEXT,
          PRIMARY KEY(tenant,id),
          FOREIGN KEY(tenant,job) REFERENCES jobs(tenant,id));
        CREATE TABLE IF NOT EXISTS invoices (
          tenant TEXT NOT NULL, id TEXT NOT NULL, job TEXT NOT NULL,
          proposal TEXT NOT NULL, total INTEGER NOT NULL, contribution INTEGER NOT NULL,
          PRIMARY KEY(tenant,id), UNIQUE(tenant,job), UNIQUE(tenant,proposal),
          FOREIGN KEY(tenant,job) REFERENCES jobs(tenant,id));
        CREATE TABLE IF NOT EXISTS payments (
          tenant TEXT NOT NULL, reference TEXT NOT NULL, invoice TEXT NOT NULL,
          amount INTEGER NOT NULL, PRIMARY KEY(tenant,reference),
          FOREIGN KEY(tenant,invoice) REFERENCES invoices(tenant,id));
        CREATE TABLE IF NOT EXISTS events (
          sequence INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
          actor TEXT NOT NULL, type TEXT NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def _require(self, ctx, roles):
        if not ctx.tenant or not ctx.actor or ctx.role not in roles:
            raise WorkflowError('Permission denied')

    def _job(self, ctx, job):
        row = self.db.execute('SELECT * FROM jobs WHERE tenant=? AND id=?', (ctx.tenant, job)).fetchone()
        if row is None:
            raise WorkflowError('Job unavailable')
        return row

    def _event(self, ctx, kind, payload):
        self.db.execute('INSERT INTO events(tenant,actor,type,at,payload) VALUES(?,?,?,?,?)',
                        (ctx.tenant, ctx.actor, kind, now().isoformat(), canonical(payload)))

    def _transaction(self, operation):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result = operation()
            self.db.execute('COMMIT')
            return result
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def create_job(self, ctx, job):
        self._require(ctx, {'dispatcher', 'owner'})
        if not isinstance(job, str) or not job.strip():
            raise WorkflowError('Job ID required')
        def op():
            self.db.execute('INSERT INTO jobs(tenant,id,version,state) VALUES(?,?,1,?)',
                            (ctx.tenant, job, 'scheduled'))
            self._event(ctx, 'job.scheduled', {'job': job})
        self._transaction(op)

    def submit_closeout(self, ctx, job, evidence):
        self._require(ctx, {'technician', 'owner'})
        if not isinstance(evidence, list) or not evidence or any(not isinstance(x, str) or not x.strip() for x in evidence):
            raise WorkflowError('Verified evidence references required')
        def op():
            row = self._job(ctx, job)
            if row['state'] not in {'scheduled', 'closeout_submitted'}:
                raise WorkflowError('Closeout cannot change after invoicing')
            self.db.execute('UPDATE jobs SET version=version+1,state=?,evidence=? WHERE tenant=? AND id=?',
                            ('closeout_submitted', canonical(evidence), ctx.tenant, job))
            # Same canonical name as the Quality Agent trigger.
            self._event(ctx, 'job.closeout.submitted', {'job': job, 'evidence_ids': evidence})
        self._transaction(op)

    def set_hold(self, ctx, job, kind, reason, active=True):
        roles = {'quality': {'quality_reviewer'}, 'compliance': {'compliance_reviewer'},
                 'finance': {'finance_reviewer'}}
        self._require(ctx, roles.get(kind, set()))
        if not isinstance(reason, str) or not reason.strip() or type(active) is not bool:
            raise WorkflowError('Reviewed reason and explicit hold state required')
        def op():
            row = self._job(ctx, job)
            if row['state'] == 'paid':
                raise WorkflowError('Open a corrective case for a paid job')
            self.db.execute('INSERT INTO holds VALUES(?,?,?,?,?) ON CONFLICT(tenant,job,kind) DO UPDATE SET reason=excluded.reason,active=excluded.active',
                            (ctx.tenant, job, kind, reason, int(active)))
            self.db.execute('UPDATE jobs SET version=version+1 WHERE tenant=? AND id=?', (ctx.tenant, job))
            self._event(ctx, 'hold.changed', {'job': job, 'kind': kind, 'active': active, 'reason': reason})
        self._transaction(op)

    def propose_invoice(self, ctx, job, *, revenue, direct_cost, selling_cost, tax, ttl_seconds=900):
        self._require(ctx, {'finance', 'owner'})
        amounts = {k: money(v) for k, v in dict(revenue=revenue, direct_cost=direct_cost, selling_cost=selling_cost, tax=tax).items()}
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise WorkflowError('Approval lifetime must be 1–3600 seconds')
        def op():
            row = self._job(ctx, job)
            if row['state'] != 'closeout_submitted':
                raise WorkflowError('Documented closeout required')
            body = dict(amounts, evidence=json.loads(row['evidence']), job=job, version=row['version'],
                        policy_version='pilot-v1', currency='USD')
            pid = str(uuid4())
            self.db.execute('INSERT INTO proposals(tenant,id,job,version,requester,body,hash,expires) VALUES(?,?,?,?,?,?,?,?)',
                            (ctx.tenant, pid, job, row['version'], ctx.actor, canonical(body), digest(body),
                             (now()+timedelta(seconds=ttl_seconds)).isoformat()))
            self._event(ctx, 'proposal.created', {'proposal': pid, 'hash': digest(body)})
            return pid
        return self._transaction(op)

    def _proposal(self, ctx, pid):
        p = self.db.execute('SELECT * FROM proposals WHERE tenant=? AND id=?', (ctx.tenant, pid)).fetchone()
        if p is None:
            raise WorkflowError('Proposal unavailable')
        if now() >= datetime.fromisoformat(p['expires']):
            raise WorkflowError('Proposal expired')
        if digest(json.loads(p['body'])) != p['hash']:
            raise WorkflowError('Proposal integrity failure')
        job = self._job(ctx, p['job'])
        if job['version'] != p['version']:
            raise WorkflowError('Source changed; create a new proposal')
        if self.db.execute('SELECT 1 FROM holds WHERE tenant=? AND job=? AND active=1', (ctx.tenant, p['job'])).fetchone():
            raise WorkflowError('Independent hold blocks action')
        return p

    def approve(self, ctx, pid):
        self._require(ctx, {'finance_reviewer'})
        def op():
            p = self._proposal(ctx, pid)
            if p['requester'] == ctx.actor:
                raise WorkflowError('Requester cannot approve own proposal')
            self.db.execute('UPDATE proposals SET approver=?,approved_hash=? WHERE tenant=? AND id=?',
                            (ctx.actor, p['hash'], ctx.tenant, pid))
            self._event(ctx, 'proposal.approved', {'proposal': pid, 'hash': p['hash']})
        self._transaction(op)

    def execute_invoice(self, ctx, pid):
        self._require(ctx, {'finance', 'owner'})
        def op():
            # A committed action remains replayable after its source version advances.
            existing = self.db.execute('SELECT * FROM invoices WHERE tenant=? AND proposal=?', (ctx.tenant, pid)).fetchone()
            if existing:
                return dict(existing)
            p = self._proposal(ctx, pid)
            if not p['approver'] or p['approved_hash'] != p['hash']:
                raise WorkflowError('Exact proposal approval required')
            body = json.loads(p['body'])
            iid = str(uuid4())
            total = body['revenue'] + body['tax']
            contribution = body['revenue'] - body['direct_cost'] - body['selling_cost']
            self.db.execute('INSERT INTO invoices VALUES(?,?,?,?,?,?)', (ctx.tenant, iid, p['job'], pid, total, contribution))
            self.db.execute('UPDATE jobs SET state=?,version=version+1 WHERE tenant=? AND id=?', ('invoiced', ctx.tenant, p['job']))
            self._event(ctx, 'invoice.created', {'invoice': iid, 'job': p['job'], 'total_minor': total})
            return dict(self.db.execute('SELECT * FROM invoices WHERE tenant=? AND id=?', (ctx.tenant, iid)).fetchone())
        return self._transaction(op)

    def record_payment(self, ctx, invoice, reference, amount):
        self._require(ctx, {'finance_reviewer'})
        money(amount)
        if amount == 0 or not isinstance(reference, str) or not reference.strip():
            raise WorkflowError('Positive payment and provider reference required')
        def op():
            inv = self.db.execute('SELECT * FROM invoices WHERE tenant=? AND id=?', (ctx.tenant, invoice)).fetchone()
            if inv is None:
                raise WorkflowError('Invoice unavailable')
            old = self.db.execute('SELECT * FROM payments WHERE tenant=? AND reference=?', (ctx.tenant, reference)).fetchone()
            if old:
                if old['invoice'] != invoice or old['amount'] != amount:
                    raise WorkflowError('Payment reference conflict')
                return
            paid = self.db.execute('SELECT COALESCE(SUM(amount),0) FROM payments WHERE tenant=? AND invoice=?', (ctx.tenant, invoice)).fetchone()[0]
            if paid + amount > inv['total']:
                raise WorkflowError('Payment exceeds balance; reconcile separately')
            self.db.execute('INSERT INTO payments VALUES(?,?,?,?)', (ctx.tenant, reference, invoice, amount))
            if paid + amount == inv['total']:
                self.db.execute('UPDATE jobs SET state=?,version=version+1 WHERE tenant=? AND id=?', ('paid', ctx.tenant, inv['job']))
            self._event(ctx, 'payment.recorded', {'invoice': invoice, 'reference': reference, 'amount_minor': amount})
        self._transaction(op)

    def snapshot(self, ctx):
        self._require(ctx, {'owner', 'finance', 'finance_reviewer', 'dispatcher', 'quality_reviewer', 'compliance_reviewer'})
        return {table: [dict(r) for r in self.db.execute(f'SELECT * FROM {table} WHERE tenant=?', (ctx.tenant,))]
                for table in ('jobs', 'holds', 'proposals', 'invoices', 'payments', 'events')}
