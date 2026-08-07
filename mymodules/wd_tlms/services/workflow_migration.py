# -*- coding: utf-8 -*-
from odoo import models


class WorkflowMigration(models.AbstractModel):
    """Sprint50-A state migration service with dry_run / execute modes."""

    _name = 'tlmp.workflow.migration'
    _description = 'Sprint50-A State Migration'

    def _steps(self):
        return [
            ('request confirmed -> submitted',
             self.env['tlmp.transport.request'].sudo().search([
                 ('state', '=', 'confirmed')]),
             {'state': 'submitted', 'validation_state': 'passed'}),
            ('inquiry accepted -> closed',
             self.env['tlmp.transport.inquiry'].sudo().search([
                 ('state', '=', 'accepted')]),
             {'state': 'closed', 'close_reason': 'carrier_selected'}),
            ('inquiry responded -> sent',
             self.env['tlmp.transport.inquiry'].sudo().search([
                 ('state', '=', 'responded')]),
             {'state': 'sent'}),
            ('inquiry rejected/expired -> cancelled',
             self.env['tlmp.transport.inquiry'].sudo().search([
                 ('state', 'in', ('rejected', 'expired'))]),
             {'state': 'cancelled', 'close_reason': 'customer_cancelled'}),
            ('quote sent -> issued',
             self.env['tlmp.transport.quote'].sudo().search([
                 ('state', '=', 'sent')]),
             {'state': 'issued'}),
            ('quote accepted -> confirmed',
             self.env['tlmp.transport.quote'].sudo().search([
                 ('state', '=', 'accepted')]),
             {'state': 'confirmed', 'confirmation_source': 'customer'}),
            ('order assigned -> allocated',
             self.env['tlmp.transport.order'].sudo().search([
                 ('state', '=', 'assigned')]),
             {'state': 'allocated'}),
            ('order signed -> delivered',
             self.env['tlmp.transport.order'].sudo().search([
                 ('state', '=', 'signed')]),
             {'state': 'delivered'}),
            ('order billed -> settlement_pending',
             self.env['tlmp.transport.order'].sudo().search([
                 ('state', '=', 'billed')]),
             {'state': 'settlement_pending'}),
            ('order closed -> settled',
             self.env['tlmp.transport.order'].sudo().search([
                 ('state', '=', 'closed')]),
             {'state': 'settled'}),
            ('container plan confirmed -> reserved',
             self.env['container.transport.plan'].sudo().search([
                 ('state', '=', 'confirmed')]),
             {'state': 'reserved', 'reservation_type': 'vehicle'}),
            ('container plan completed -> finished',
             self.env['container.transport.plan'].sudo().search([
                 ('state', '=', 'completed')]),
             {'state': 'finished'}),
        ]

    def run(self, dry_run=False):
        """Return mapping report; only apply writes when dry_run=False."""
        report = []
        for label, records, vals in self._steps():
            count = len(records)
            report.append({'step': label, 'affected': count})
            if not dry_run and count:
                records.write(vals)
        return report
