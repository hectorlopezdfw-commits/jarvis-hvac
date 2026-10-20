import hashlib
import tempfile
import unittest
from pathlib import Path
from app.controls.access import Access, Gateway
from app.controls.core import Store, WorkflowError


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name)/'access.sqlite')
        self.store = Store(self.path)
        self.access = Access(self.store)
        self.gateway = Gateway(self.access)
        self.access.provision('a', 'alice', 'owner')
        self.token = self.access.issue('a', 'alice')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_persisted_session_and_hash_only_storage(self):
        row = self.store.db.execute('SELECT * FROM sessions').fetchone()
        self.assertEqual(row['token_hash'], hashlib.sha256(self.token.encode()).hexdigest())
        self.assertNotIn(self.token, str(self.store.snapshot(self.access.resolve(self.token))))
        second = Store(self.path)
        try:
            self.assertEqual(Access(second).resolve(self.token).actor, 'alice')
        finally:
            second.close()

    def test_gateway_uses_stored_identity(self):
        self.gateway.call(self.token, 'create_job', {'job':'j1'})
        self.access.provision('b', 'bob', 'owner')
        other = self.access.issue('b', 'bob')
        self.assertEqual(self.gateway.call(other, 'snapshot')['jobs'], [])
        with self.assertRaises(WorkflowError):
            self.gateway.call(other, 'submit_closeout', {'job':'j1', 'evidence':['e']})
        with self.assertRaises(WorkflowError):
            self.gateway.call(other, 'snapshot', {'tenant':'a'})

    def test_unknown_actions_and_context_injection(self):
        for action in ('provision', 'issue', '_event', 'close', 'db'):
            with self.assertRaises(WorkflowError):
                self.gateway.call(self.token, action)
        for key in ('ctx', 'role', 'tenant', 'actor'):
            with self.assertRaises(WorkflowError):
                self.gateway.call(self.token, 'snapshot', {key:'injected'})
        with self.assertRaises(WorkflowError):
            self.gateway.call(self.token, 'create_job', {'unexpected':True})

    def test_expired_revoked_and_invalid_sessions(self):
        for token in ('bad', 'x'*43, None):
            with self.assertRaises(WorkflowError):
                self.gateway.call(token, 'snapshot')
        self.store.db.execute("UPDATE sessions SET expires='2000-01-01T00:00:00+00:00'")
        with self.assertRaises(WorkflowError):
            self.gateway.call(self.token, 'snapshot')
        token = self.access.issue('a', 'alice')
        self.access.revoke(token)
        with self.assertRaises(WorkflowError):
            self.gateway.call(token, 'snapshot')

    def test_role_change_and_suspension_invalidate_sessions(self):
        self.access.provision('a', 'alice', 'technician')
        with self.assertRaises(WorkflowError):
            self.gateway.call(self.token, 'create_job', {'job':'j1'})
        token = self.access.issue('a', 'alice')
        with self.assertRaises(WorkflowError):
            self.gateway.call(token, 'create_job', {'job':'j1'})
        self.access.disable('a', 'alice')
        with self.assertRaises(WorkflowError):
            self.access.resolve(token)
        with self.assertRaises(WorkflowError):
            self.access.issue('a', 'alice')

    def test_invalid_provision_and_lifetime(self):
        for role in ('admin', '', None):
            with self.assertRaises(WorkflowError):
                self.access.provision('a','x',role)
        for ttl in (True, 0, 3601, 1.5):
            with self.assertRaises(WorkflowError):
                self.access.issue('a','alice',ttl)


if __name__ == '__main__':
    unittest.main()
