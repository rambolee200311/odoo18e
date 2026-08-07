# -*- coding: utf-8 -*-
"""Sprint50-A: apply five-model state convergence migration."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['tlmp.workflow.migration'].sudo().run(dry_run=False)
