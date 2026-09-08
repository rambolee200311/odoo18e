# © 2024 Wukong Digital. License LGPL-3.
"""Creation of draft vendor bills from the reviewed value object only."""

from decimal import Decimal, InvalidOperation

from odoo import _
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Command

from . import validation_service


def _number(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _line_vals(line, fallback_product=None):
    quantity = _number(line.get("quantity"), "1")
    if not quantity:
        quantity = Decimal("1")
    unit_price = line.get("unit_price")
    if unit_price is None:
        subtotal = line.get("subtotal")
        if subtotal is None:
            subtotal = line.get("line_total_amount")
        unit_price = _number(subtotal) / quantity

    vals = {
        "name": line.get("description") or (
            fallback_product.display_name if fallback_product else _("Vendor invoice line")
        ),
        "quantity": float(quantity),
        "price_unit": float(_number(unit_price)),
        "tax_ids": [Command.set(line.get("tax_ids") or [])],
        "reconciliation_clues": line.get("reconciliation_clues") or [],
    }
    if line.get("statement_line_id"):
        vals["vendor_statement_line_id"] = line["statement_line_id"]
    if line.get("product_id"):
        vals["product_id"] = line["product_id"]
    elif fallback_product:
        vals["product_id"] = fallback_product.id
    return vals


def _convert_review_to_move_vals(review_result, default_product):
    header = review_result["header"]
    lines = review_result.get("lines") or []
    if lines:
        invoice_lines = [_line_vals(line) for line in lines]
    else:
        if not default_product:
            raise ValidationError(
                _("A default fallback product is required for an invoice without lines.")
            )
        invoice_lines = [_line_vals({
            "description": default_product.display_name,
            "quantity": "1",
            "unit_price": header["total_amount"],
            "tax_ids": [],
        }, fallback_product=default_product)]

    return {
        "move_type": "in_invoice",
        "partner_id": header["supplier_id"],
        "invoice_date": header["invoice_date"],
        "currency_id": header["currency_id"],
        "ref": header["invoice_number"],
        "vendor_invoice_statement_id": review_result.get("statement_id"),
        "invoice_line_ids": [Command.create(line) for line in invoice_lines],
    }


def _audit(env, task, action, summary):
    env["vendor.invoice.import.log"].create({
        "task_id": task.id,
        "parse_attempt_id": task.current_parse_attempt_id.id,
        "action": action,
        "snapshot_delta": summary,
    })


def _create_locked(env, task):
    # The task carries the authoritative company for asynchronous workers.
    env = task.env
    if task.state != "awaiting_review":
        raise ValidationError(
            _("A bill can only be created for a task awaiting review.")
        )
    if not task.human_reviewed:
        raise ValidationError(_("The task must be marked as human reviewed."))
    review_result = task.human_review_result
    if not review_result:
        raise ValidationError(_("A non-empty human review result is required."))
    if task.vendor_bill_id:
        raise ValidationError(_("A bill has already been generated for this task."))

    if task.statement_required and not task.statement_id:
        raise ValidationError(_("A Statement is required before creating a bill."))
    if task.statement_id:
        if task.statement_id.state != "confirmed":
            raise ValidationError(
                _("A Statement must be confirmed before creating a bill.")
            )
        from .statement_projection import assert_projection_consistent

        assert_projection_consistent(task.statement_id, review_result)
    validation_service.pre_check_integrity(review_result)
    config = env["wd.system.config"].get_config()
    warnings = validation_service.check_amount_balance(
        review_result, task.company_id, config.amount_tolerance
    )
    task.write({"review_warnings": warnings})

    move_vals = _convert_review_to_move_vals(
        review_result, config.default_product_id
    )
    # Keep this explicit even though the task environment has been switched to
    # the task company: asynchronous jobs do not inherit the request company.
    move_vals["company_id"] = task.company_id.id
    bill = env["account.move"].create(move_vals)

    task.source_pdf_attachment_id.copy({
        "res_model": "account.move",
        "res_id": bill.id,
        "public": False,
    })
    task.write({
        "vendor_bill_id": bill.id,
        "state": "bill_generated",
    })
    task.statement_id._aggregate_write({
        "vendor_bill_id": bill.id,
        "state": "bill_created",
    })
    task._log_statement_change(
        "statement_bill_created",
        task.statement_id.source_parse_attempt_id,
        "Draft vendor bill %s linked to Statement." % bill.display_name,
    )
    _audit(env, task, "bill_create", "Draft vendor bill %s created." % bill.display_name)
    return bill


def create_vendor_bill(env, task_id):
    """Create one draft bill in the caller's transaction."""
    with env.cr.savepoint():
        task = env["wd.lock.service"].lock_task(task_id)
        task.ensure_one()
        task = task.with_company(task.company_id)
        return _create_locked(env, task)


def confirm_review_and_create_bill(env, task_id, review_payload):
    """Persist review data and create the bill as one atomic operation."""
    if not env.user.has_group("ai_vendor_invoice.group_reviewer"):
        raise AccessError(_("Only an invoice reviewer can confirm a bill."))
    if not isinstance(review_payload, dict) or not review_payload:
        raise ValidationError(_("A non-empty review result is required."))

    with env.cr.savepoint():
        task = env["wd.lock.service"].lock_task(task_id)
        task.ensure_one()
        task = task.with_company(task.company_id)
        if task.state != "awaiting_review":
            raise ValidationError(
                _("Only an invoice awaiting review can be confirmed.")
            )
        if task.statement_id:
            task.action_confirm_statement(review_payload)
        else:
            task.write({
                "human_review_result": review_payload,
                "human_reviewed": True,
            })
        _audit(env, task, "human_modify", "Human review confirmed.")
        return _create_locked(env, task)
