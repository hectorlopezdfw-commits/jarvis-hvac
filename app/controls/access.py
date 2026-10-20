"""Local session boundary. Provisioning is a trusted administrative operation.

No password login or public server is supplied. A future identity provider must
verify a person before an administrator provisions membership and issues a token.
"""
import hashlib
import secrets
from datetime import timedelta
from .core import Context, WorkflowError, now

ROLES = frozenset({'owner', 'dispatcher', 'technician', 'finance',
                   'finance_reviewer', 'quality_reviewer', 'compliance_reviewer', 'platform_admin'})


class Access:
    def __init__(self, store):
        self.store = store
        store.db.executescript('''
        CREATE TABLE IF NOT EXISTS memberships (
          tenant TEXT NOT NULL, actor TEXT NOT NULL, role TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(tenant,actor));
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, tenant TEXT NOT NULL, actor TEXT NOT NULL,
          expires TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(tenant,actor) REFERENCES memberships(tenant,actor));
        ''')

    def provision(self, tenant, actor, role):
        """Trusted admin-only API; deliberately excluded from the session gateway."""
        if any(not isinstance(x, str) or not x.strip() for x in (tenant, actor)) or role not in ROLES:
            raise WorkflowError('Valid tenant, actor and role required')
        def op():
            self.store.db.execute('INSERT INTO memberships VALUES(?,?,?,1) ON CONFLICT(tenant,actor) DO UPDATE SET role=excluded.role,active=1',
                                  (tenant, actor, role))
            # Reprovisioning invalidates existing sessions, including role changes.
            self.store.db.execute('UPDATE sessions SET revoked=1 WHERE tenant=? AND actor=?', (tenant, actor))
            self.store._event(Context(tenant, 'local-admin', 'owner'), 'membership.provisioned', {'actor': actor, 'role': role})
        self.store._transaction(op)

    def issue(self, tenant, actor, ttl_seconds=900):
        """Trusted issuer only; possession of tenant/actor IDs is not authentication."""
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
            raise WorkflowError('Session lifetime must be 1–3600 seconds')
        token = secrets.token_urlsafe(32)
        def op():
            member = self.store.db.execute('SELECT * FROM memberships WHERE tenant=? AND actor=? AND active=1', (tenant, actor)).fetchone()
            if member is None:
                raise WorkflowError('Membership unavailable')
            self.store.db.execute('INSERT INTO sessions(token_hash,tenant,actor,expires) VALUES(?,?,?,?)',
                                  (self._hash(token), tenant, actor, (now()+timedelta(seconds=ttl_seconds)).isoformat()))
            self.store._event(Context(tenant, actor, member['role']), 'session.issued', {})
        self.store._transaction(op)
        return token

    @staticmethod
    def _hash(token):
        if not isinstance(token, str) or not 20 <= len(token) <= 256:
            raise WorkflowError('Invalid session')
        return hashlib.sha256(token.encode()).hexdigest()

    def resolve(self, token):
        from datetime import datetime
        row = self.store.db.execute('''SELECT s.*,m.role,m.active FROM sessions s
            JOIN memberships m ON s.tenant=m.tenant AND s.actor=m.actor
            WHERE s.token_hash=?''', (self._hash(token),)).fetchone()
        if row is None or row['revoked'] or not row['active'] or now() >= datetime.fromisoformat(row['expires']):
            raise WorkflowError('Invalid session')
        return Context(row['tenant'], row['actor'], row['role'])

    def revoke(self, token):
        def op():
            ctx = self.resolve(token)
            self.store.db.execute('UPDATE sessions SET revoked=1 WHERE token_hash=?', (self._hash(token),))
            self.store._event(ctx, 'session.revoked', {})
        self.store._transaction(op)

    def disable(self, tenant, actor):
        """Trusted administrative account suspension; all sessions stop working."""
        def op():
            self.store.db.execute('UPDATE memberships SET active=0 WHERE tenant=? AND actor=?', (tenant, actor))
            self.store.db.execute('UPDATE sessions SET revoked=1 WHERE tenant=? AND actor=?', (tenant, actor))
            self.store._event(Context(tenant, 'local-admin', 'owner'), 'membership.disabled', {'actor': actor})
        self.store._transaction(op)


class Gateway:
    """Allowlisted workflow boundary. Identity fields are never client parameters.

    Do not expose Access.provision/issue/disable as unauthenticated HTTP endpoints.
    Keep the underlying store and Access object private to trusted application code.
    """
    ACTIONS = frozenset({'create_job', 'submit_closeout', 'set_hold', 'propose_invoice',
                         'approve', 'execute_invoice', 'record_payment', 'snapshot'})

    def __init__(self, access):
        self.access = access

    def call(self, token, action, parameters=None):
        if action not in self.ACTIONS:
            raise WorkflowError('Unknown action')
        if parameters is None:
            parameters = {}
        if not isinstance(parameters, dict) or any(k in parameters for k in ('ctx', 'tenant', 'actor', 'role')):
            raise WorkflowError('Identity parameters are forbidden')
        # Resolve membership on every request; never cache client-supplied roles.
        ctx = self.access.resolve(token)
        method = getattr(self.access.store, action)
        import inspect
        try:
            inspect.signature(method).bind(ctx, **parameters)
        except TypeError as error:
            raise WorkflowError('Invalid action parameters') from error
        return method(ctx, **parameters)
