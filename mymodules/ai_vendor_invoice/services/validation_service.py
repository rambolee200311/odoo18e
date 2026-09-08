# © 2024 Wukong Digital. License LGPL-3.
"""Business-independent checks used immediately before creating a vendor bill."""

from decimal import Decimal, InvalidOperation
from datetime import date

from odoo import _
from odoo.exceptions import ValidationError


def _blank(value):
    return value is None or value is False or (
        isinstance(value, str) and not value.strip()
    )


def _amount(value):
    if _blank(value):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def pre_check_integrity(review_result):
    """Raise :class:`ValidationError` when a review cannot form an invoice."""
    if not isinstance(review_result, dict) or not review_result:
        raise ValidationError(_("A non-empty human review result is required."))

    header = review_result.get("header")
    if not isinstance(header, dict):
        raise ValidationError(_("Human review header is required."))

    required = {
        "supplier_id": _("A supplier is required."),
        "invoice_number": _("An invoice number is required."),
        "invoice_date": _("An invoice date is required."),
        "currency_id": _("An invoice currency is required."),
        "total_amount": _("A total amount is required."),
    }
    for field_name, message in required.items():
        if _blank(header.get(field_name)):
            raise ValidationError(message)

    try:
        date.fromisoformat(str(header["invoice_date"]))
    except (TypeError, ValueError):
        raise ValidationError(_("The invoice date must be a valid ISO date."))

    if not isinstance(header["supplier_id"], int) or header["supplier_id"] <= 0:
        raise ValidationError(_("The supplier must be a valid partner."))
    if not isinstance(header["currency_id"], int) or header["currency_id"] <= 0:
        raise ValidationError(_("The currency must be valid."))
    if _amount(header["total_amount"]) is None:
        raise ValidationError(_("The total amount must be numeric."))

    lines = review_result.get("lines", [])
    if lines is None:
        lines = []
    if not isinstance(lines, list):
        raise ValidationError(_("Invoice lines must be a list."))

    for index, line in enumerate(lines, start=1):
        if not isinstance(line, dict):
            raise ValidationError(_("Invoice line %s is invalid.") % index)
        taxes = line.get("tax_ids")
        if not isinstance(taxes, list) or not taxes or any(
            not isinstance(tax_id, int) or tax_id <= 0 for tax_id in taxes
        ):
            raise ValidationError(
                _("Invoice line %s must have a valid tax configuration.") % index
            )


def check_amount_balance(review_result, company=None, tolerance=Decimal("0.01")):
    """Return warnings for an amount mismatch; never block bill creation."""
    header = (review_result or {}).get("header") or {}
    expected = _amount(header.get("total_amount"))
    lines = (review_result or {}).get("lines") or []
    if expected is None or not lines:
        return []

    total = Decimal("0")
    invalid_line = False
    for line in lines:
        value = _amount(line.get("line_total_amount"))
        if value is None:
            subtotal = _amount(line.get("subtotal"))
            tax = _amount(line.get("tax_amount")) or Decimal("0")
            value = subtotal + tax if subtotal is not None else None
        if value is None:
            invalid_line = True
            continue
        total += value

    if invalid_line or abs(total - expected) > Decimal(str(tolerance)):
        return [{
            "code": "AMOUNT_MISMATCH",
            "message": _(
                "Invoice total %(expected)s does not match invoice lines %(actual)s."
            ) % {"expected": str(expected), "actual": str(total)},
        }]
    return []
