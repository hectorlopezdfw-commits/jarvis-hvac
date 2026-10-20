import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from app.controls.core import Context, Store, WorkflowError


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name)/'pilot.sqlite')
        self.store = Store(self.path)
        self.owner = Context('a', 'owner', 'owner')
        self.finance = Context('a', 'preparer', 'finance')
        self.reviewer = Context('a', 'reviewer', 'finance_reviewer')
        self.store.create_job(self.owner, 'job1')
        self.store.submit_closeout(self.owner, 'job1', ['synthetic-evidence-1'])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def proposal(self):
        return self.store.propose_invoice(self.finance, 'job1', revenue=100000, direct_cost=60000, selling_cost=5000, tax=8250)

    def invoice(self):
        pid = self.proposal()
        self.store.approve(self.reviewer, pid)
        return self.store.execute_invoice(self.finance, pid)

    def test_complete_flow_partial_payments_and_replay(self):
        inv = self.invoice()
        self.assertEqual((inv['total'], inv['contribution']), (108250, 35000))
        self.store.record_payment(self.reviewer, inv['id'], 'payment-1', 50000)
        self.store.record_payment(self.reviewer, inv['id'], 'payment-1', 50000)
        self.assertEqual(self.store.snapshot(self.owner)['jobs'][0]['state'], 'invoiced')
        self.store.record_payment(self.reviewer, inv['id'], 'payment-2', 58250)
        self.assertEqual(self.store.snapshot(self.owner)['jobs'][0]['state'], 'paid')
        self.assertEqual(len(self.store.snapshot(self.owner)['payments']), 2)

    def test_tenant_isolation(self):
        other = Context('b', 'owner', 'owner')
        self.assertEqual(self.store.snapshot(other)['jobs'], [])
        with self.assertRaises(WorkflowError):
            self.store.submit_closeout(other, 'job1', ['e'])
        pid = self.proposal()
        with self.assertRaises(WorkflowError):
            self.store.approve(Context('b', 'reviewer', 'finance_reviewer'), pid)
        self.store.create_job(other, 'job1')
        self.assertEqual(len(self.store.snapshot(other)['jobs']), 1)

    def test_requires_approval_and_separation(self):
        pid = self.proposal()
        with self.assertRaises(WorkflowError):
            self.store.execute_invoice(self.finance, pid)
        with self.assertRaises(WorkflowError):
            self.store.approve(Context('a', 'preparer', 'finance_reviewer'), pid)

    def test_changed_evidence_invalidates_approval(self):
        pid = self.proposal()
        self.store.approve(self.reviewer, pid)
        self.store.submit_closeout(self.owner, 'job1', ['replacement-evidence'])
        with self.assertRaisesRegex(WorkflowError, 'Source changed'):
            self.store.execute_invoice(self.finance, pid)

    def test_hold_cannot_be_overridden_by_owner(self):
        quality = Context('a', 'quality', 'quality_reviewer')
        self.store.set_hold(quality, 'job1', 'quality', 'Missing measurement')
        with self.assertRaises(WorkflowError):
            self.store.set_hold(self.owner, 'job1', 'quality', 'Owner override', False)
        pid = self.proposal()
        with self.assertRaisesRegex(WorkflowError, 'hold'):
            self.store.approve(self.reviewer, pid)
        self.store.set_hold(quality, 'job1', 'quality', 'Measurement verified', False)
        with self.assertRaisesRegex(WorkflowError, 'Source changed'):
            self.store.approve(self.reviewer, pid)
        self.invoice()

    def test_expiry_and_tampering(self):
        pid = self.proposal()
        self.store.db.execute("UPDATE proposals SET expires='2000-01-01T00:00:00+00:00' WHERE id=?", (pid,))
        with self.assertRaisesRegex(WorkflowError, 'expired'):
            self.store.approve(self.reviewer, pid)
        pid2 = self.proposal()
        self.store.db.execute("UPDATE proposals SET body='{}' WHERE id=?", (pid2,))
        with self.assertRaisesRegex(WorkflowError, 'integrity'):
            self.store.approve(self.reviewer, pid2)

    def test_concurrent_replays_commit_one_invoice(self):
        pid = self.proposal()
        self.store.approve(self.reviewer, pid)
        def execute(_):
            store = Store(self.path)
            try:
                return store.execute_invoice(self.finance, pid)['id']
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(execute, range(10)))
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(self.store.snapshot(self.owner)['invoices']), 1)
        self.assertEqual(sum(e['type']=='invoice.created' for e in self.store.snapshot(self.owner)['events']), 1)

    def test_unknown_cost_and_overpayment_blocked(self):
        for bad in (None, True, 1.5, -1):
            with self.assertRaises(WorkflowError):
                self.store.propose_invoice(self.finance, 'job1', revenue=100, direct_cost=bad, selling_cost=0, tax=0)
        inv = self.invoice()
        with self.assertRaises(WorkflowError):
            self.store.record_payment(self.reviewer, inv['id'], 'too-much', inv['total']+1)
        self.assertEqual(self.store.snapshot(self.owner)['payments'], [])

    def test_payment_reference_conflict(self):
        inv = self.invoice()
        self.store.record_payment(self.reviewer, inv['id'], 'p1', 1)
        with self.assertRaises(WorkflowError):
            self.store.record_payment(self.reviewer, inv['id'], 'p1', 2)

    def test_example_routes_to_quality(self):
        root = Path(__file__).resolve().parent.parent/'docs'/'blueprint'
        agents = json.loads((root/'agent_contracts.json').read_text())['agents']
        quality = next(a for a in agents if a['id']=='qua')
        sample = json.loads((root/'events.example.json').read_text())[0]
        self.assertIn(sample['event_type'], quality['triggers'])
        self.assertIn('job.closeout.submitted', [e['type'] for e in self.store.snapshot(self.owner)['events']])


if __name__ == '__main__':
    unittest.main()
