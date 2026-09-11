# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    bank_proof_attachment_ids = fields.Many2many("ir.attachment", "account_move_bank_proof_attachment_rel", "move_id", "attachment_id", string="Bank Proof Attachments", copy=False, tracking=True)
    payment_info_synced = fields.Boolean(string="Payment Information Synced", readonly=True, copy=False, tracking=True)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    charge_item_id = fields.Many2one("world.depot.charge.item", string="Charge Item", ondelete="restrict", copy=False, index=True)
