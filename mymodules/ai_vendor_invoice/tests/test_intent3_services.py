# © 2024 Wukong Digital. License LGPL-3.
"""Targeted Intent-3 tests for validation and timeout recovery."""

from datetime import timedelta
import base64
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase

from ..services import bill_creator, timeout_service, validation_service


def _review(lines=None, total="10.00"):
    return {
        "header": {
            "supplier_id": 1,
            "invoice_number": "INV-001",
            "invoice_date": "2026-08-21",
            "currency_id": 1,
            "total_amount": total,
        },
        "lines": [] if lines is None else lines,
    }


class TestValidationService(TransactionCase):

    def test_pre_check_requires_invoice_header(self):
        with self.assertRaises(ValidationError):
            validation_service.pre_check_integrity({"header": {}})

    def test_pre_check_requires_tax_on_explicit_lines(self):
        review = _review([{
            "description": "Consulting",
            "quantity": "1",
            "unit_price": "10",
        }])
        with self.assertRaises(ValidationError):
            validation_service.pre_check_integrity(review)

    def test_amount_mismatch_is_a_warning(self):
        review = _review([{
            "description": "Consulting",
            "quantity": "1",
            "unit_price": "9",
            "subtotal": "9",
            "tax_amount": "0",
            "line_total_amount": "9",
            "tax_ids": [1],
        }])
        warnings = validation_service.check_amount_balance(review, self.env.company, 0.01)
        self.assertEqual(warnings[0]["code"], "AMOUNT_MISMATCH")

    def test_amount_warning_does_not_raise(self):
        validation_service.check_amount_balance(_review(), self.env.company, 0.01)


class TestTimeoutService(TransactionCase):

    def _task_with_attempt(self, status):
        attachment = self.env["ir.attachment"].create({
            "name": "timeout.pdf",
            "datas": b"",
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Timeout provider",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": attachment.id,
            "selected_provider_config_id": provider.id,
            "state": "parsing",
        })
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": provider.id,
            "status": status,
        })
        task.write({
            "current_parse_attempt_id": attempt.id,
            "enter_parsing_datetime": fields.Datetime.now(),
        })
        return task, attempt

    def test_timeout_uses_task_entry_time_for_queued_and_running(self):
        config = self.env["wd.system.config"].get_config()
        config.write({"task_timeout_seconds": 1})
        records = []
        for status in ("queued", "running"):
            task, attempt = self._task_with_attempt(status)
            old = fields.Datetime.to_string(
                fields.Datetime.to_datetime(
                    task.enter_parsing_datetime
                ) - timedelta(seconds=10)
            )
            task.write({"enter_parsing_datetime": old})
            records.append((task, attempt))

        self.assertEqual(timeout_service.check_parsing_timeout(self.env), 2)
        for task, attempt in records:
            self.assertEqual(task.state, "error")
            self.assertEqual(attempt.status, "failed")


class TestBillCreatorGuards(TransactionCase):

    def test_creates_draft_and_copies_source_attachment(self):
        product = self.env["product.product"].search([], limit=1)
        self.assertTrue(product)
        self.env["wd.system.config"].get_config().write({
            "default_product_id": product.id,
        })
        partner = self.env["res.partner"].create({"name": "Intent-3 supplier"})
        source = self.env["ir.attachment"].create({
            "name": "source.pdf",
            "datas": base64.b64encode(b"pdf"),
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Bill provider",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": provider.id,
            "state": "awaiting_review",
            "human_reviewed": True,
            "human_review_result": _review(),
            "statement_required": False,
        })
        review = dict(task.human_review_result)
        review["header"] = dict(review["header"], supplier_id=partner.id,
                                currency_id=self.env.company.currency_id.id)
        task.write({"human_review_result": review})

        bill = bill_creator.create_vendor_bill(self.env, task.id)
        copied = self.env["ir.attachment"].search([
            ("res_model", "=", "account.move"),
            ("res_id", "=", bill.id),
        ])
        self.assertEqual(bill.move_type, "in_invoice")
        self.assertEqual(bill.company_id, task.company_id)
        self.assertEqual(task.vendor_bill_id, bill)
        self.assertTrue(copied)
        self.assertEqual(source.res_id, 0)
        with self.assertRaises(ValidationError):
            bill_creator.create_vendor_bill(self.env, task.id)
        self.assertEqual(
            self.env["account.move"].search_count([("ref", "=", "INV-001")]),
            1,
        )

    def test_bill_and_task_roll_back_when_attachment_copy_fails(self):
        product = self.env["product.product"].search([], limit=1)
        self.env["wd.system.config"].get_config().write({
            "default_product_id": product.id,
        })
        partner = self.env["res.partner"].search([], limit=1)
        source = self.env["ir.attachment"].create({
            "name": "rollback.pdf",
            "datas": base64.b64encode(b"pdf"),
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Rollback provider",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": provider.id,
            "state": "awaiting_review",
            "human_reviewed": True,
            "human_review_result": _review(),
            "statement_required": False,
        })
        review = dict(task.human_review_result)
        review["header"] = dict(
            review["header"],
            supplier_id=partner.id,
            currency_id=self.env.company.currency_id.id,
        )
        task.write({"human_review_result": review})

        with patch.object(type(source), "copy", side_effect=RuntimeError("copy failed")):
            with self.assertRaises(RuntimeError):
                bill_creator.create_vendor_bill(self.env, task.id)
        self.assertFalse(task.vendor_bill_id)
        self.assertFalse(self.env["account.move"].search([
            ("ref", "=", "INV-001"),
        ]))

    def test_bill_creator_does_not_create_before_review(self):
        attachment = self.env["ir.attachment"].create({
            "name": "review.pdf",
            "datas": b"",
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Review provider",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": attachment.id,
            "selected_provider_config_id": provider.id,
        })
        with self.assertRaises(ValidationError):
            bill_creator.create_vendor_bill(self.env, task.id)

    def test_unified_action_rejects_empty_review(self):
        attachment = self.env["ir.attachment"].create({
            "name": "review.pdf",
            "datas": b"",
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Review provider 2",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": attachment.id,
            "selected_provider_config_id": provider.id,
            "state": "awaiting_review",
        })
        if self.env.user.has_group("ai_vendor_invoice.group_reviewer"):
            with self.assertRaises(ValidationError):
                task.action_confirm_review_and_create_bill({})

    def test_non_reviewer_cannot_confirm_review(self):
        user = self.env.ref("base.user_demo", raise_if_not_found=False)
        if not user or user.has_group("ai_vendor_invoice.group_reviewer"):
            self.skipTest("No non-reviewer fixture is available.")
        source = self.env["ir.attachment"].create({
            "name": "permission.pdf",
            "datas": base64.b64encode(b"pdf"),
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Permission provider",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": provider.id,
            "state": "awaiting_review",
        })
        with self.assertRaises(AccessError):
            task.with_user(user).action_confirm_review_and_create_bill(_review())
