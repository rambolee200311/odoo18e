# © 2024 Wukong Digital. License LGPL-3.
"""Projection between the human Statement aggregate and the bill input."""

from decimal import Decimal

from odoo import _
from odoo.exceptions import ValidationError


def _text(value):
    return None if value in (False, None) else str(value)


def statement_to_human_review_result(statement):
    statement.ensure_one()
    if not statement.supplier_id or not statement.currency_id:
        raise ValidationError(_("A Statement supplier and currency are required."))
    return {
        "statement_id": statement.id,
        "header": {
            "supplier_id": statement.supplier_id.id,
            "invoice_number": statement.invoice_number,
            "invoice_date": statement.invoice_date.isoformat()
            if statement.invoice_date
            else None,
            "currency_id": statement.currency_id.id,
            "total_amount": str(Decimal(str(statement.total_amount))),
            "total_tax": str(Decimal(str(statement.total_tax))),
            "subtotal": str(Decimal(str(statement.subtotal))),
        },
        "lines": [
            {
                "statement_line_id": line.id,
                "product_id": line.product_id.id if line.product_id else None,
                "description": line.description,
                "quantity": _text(line.quantity),
                "unit_price": _text(line.price_unit),
                "subtotal": _text(line.amount),
                "tax_ids": line.tax_ids.ids,
                "tax_amount": _text(line.tax_amount),
                "tax_rate": _text(line.tax_rate),
                "tax_raw_text": line.tax_raw_text,
                "reconciliation_clue": line.reconciliation_clue,
                "charge_details": line.charge_details,
                "line_total_amount": _text(line.amount),
                "reconciliation_clues": line.reconciliation_clues or [],
            }
            for line in statement.line_ids
        ],
    }


def assert_projection_consistent(statement, projection):
    expected = statement_to_human_review_result(statement)
    if expected != projection:
        raise ValidationError(
            _("The HumanReviewResult projection is inconsistent with the Statement.")
        )
    return True
