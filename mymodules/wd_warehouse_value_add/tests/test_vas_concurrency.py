# -*- coding: utf-8 -*-

from odoo import api, SUPERUSER_ID
from odoo import sql_db
from psycopg2.errors import LockNotAvailable
from odoo.tests.common import TransactionCase


class TestVasConcurrency(TransactionCase):
    def setUp(self):
        super().setUp()
        self.VasOrder = self.env['wd.vas.order']
        self.warehouse = self.env['stock.warehouse'].search([], limit=1)
        with self.registry.cursor() as cursor:
            env = api.Environment(cursor, SUPERUSER_ID, {})
            self.order = env['wd.vas.order'].create({
                'order_type': 'inbound',
                'warehouse_order_billno': 'CONC-CC02',
                'warehouse_id': self.warehouse.id,
            })
            cursor.commit()
        self.order = self.VasOrder.browse(self.order.id)

    def tearDown(self):
        if self.order.exists():
            with self.registry.cursor() as cursor:
                env = api.Environment(cursor, SUPERUSER_ID, {})
                env['wd.vas.order'].browse(self.order.id).unlink()
                cursor.commit()
        super().tearDown()

    def test_vas_row_lock_blocks_second_cursor_until_release(self):
        db = sql_db.db_connect(self.env.cr.dbname)
        first_cursor = db.cursor()
        second_cursor = db.cursor()
        try:
            first_env = api.Environment(first_cursor, SUPERUSER_ID, {})
            first_env['wd.vas.order'].browse(self.order.id)._lock_for_update()

            second_cursor.execute("SET LOCAL lock_timeout = '200ms'")
            second_env = api.Environment(second_cursor, SUPERUSER_ID, {})
            with self.assertRaises(LockNotAvailable):
                second_env['wd.vas.order'].browse(self.order.id)._lock_for_update()

            first_cursor.close()
            second_cursor.rollback()
            second_env['wd.vas.order'].browse(self.order.id)._lock_for_update()
        finally:
            if not first_cursor.closed:
                first_cursor.close()
            if not second_cursor.closed:
                second_cursor.close()
