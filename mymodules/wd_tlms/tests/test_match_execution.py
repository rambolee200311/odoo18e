from odoo.tests.common import TransactionCase

class TestMatchExecution(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Execution = self.env['tlmp.carrier.match.execution']

    def test_01_create_execution(self):
        e = self.Execution.create({})
        self.assertTrue(e.id)
        self.assertEqual(e.state, 'running')

    def test_02_execution_done(self):
        e = self.Execution.create({})
        e._done(matched=5, failed=1, state='completed')
        self.assertEqual(e.state, 'completed')
        self.assertEqual(e.matched_count, 5)
        self.assertEqual(e.failed_count, 1)
        self.assertTrue(e.end_time)
