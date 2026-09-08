# © 2024 Wukong Digital. License LGPL-3.
"""Traceability links from generated vendor bills to the reviewed Statement."""

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    vendor_invoice_statement_id = fields.Many2one(
        "vendor.invoice.statement",
        string="Vendor Invoice Statement",
        ondelete="restrict",
        index=True,
        copy=False,
    )


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    vendor_statement_line_id = fields.Many2one(
        "vendor.invoice.statement.line",
        string="Vendor Statement Line",
        ondelete="restrict",
        index=True,
        copy=False,
    )
    reconciliation_clues = fields.Json(
        string="Reconciliation Clues",
        help="Generic invoice-line clues preserved for future reconciliation.",
        copy=False,
    )
