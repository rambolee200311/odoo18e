# © 2024 Wukong Digital. License LGPL-3.
"""
Intent-1 Foundation: model-only tests.
Covers: field definitions, DB constraints, immutability guards, schema
        validation, and lock_service signatures.
"""
import base64
import jsonschema
from unittest.mock import patch
from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase

from ..schemas.canonical import CANONICAL_INVOICE_RESULT_SCHEMA
from ..schemas.human_review import HUMAN_REVIEW_RESULT_SCHEMA
from ..schemas.mapping import MAPPING_RESULT_SCHEMA
from ..schemas.warning import REVIEW_WARNINGS_SCHEMA
from ..models.import_parse_attempt import VendorInvoiceImportParseAttempt


def _minimal_canonical(is_multi=False):
    """Build a minimal valid CanonicalInvoiceResult fixture."""
    field = {"value": None, "confidence": 0.0}
    return {
        "header": {
            "invoice_number": field,
            "invoice_date": field,
            "supplier_raw_text": field,
            "currency_raw_text": field,
            "total_amount": field,
            "total_tax": field,
        },
        "lines": [],
        "is_multi_invoice": is_multi,
    }


class TestImportTaskModel(TransactionCase):
    """Tests for vendor.invoice.import.task model (no AI services)."""

    def _make_attachment(self):
        return self.env["ir.attachment"].create(
            {
                "name": "test.pdf",
                "datas": b"",
                "res_model": "vendor.invoice.import.task",
            }
        )

    def _make_provider(self):
        return self.env["wd.ai.provider.config"].create(
            {
                "name": "Test Provider",
                "api_base_url": "https://example.com",
                "model_name": "test-model",
            }
        )

    def _make_task(self):
        return self.env["vendor.invoice.import.task"].create(
            {
                "source_pdf_attachment_id": self._make_attachment().id,
                "selected_provider_config_id": self._make_provider().id,
            }
        )

    # ── field & default tests ─────────────────────────────────────────────────

    def test_task_default_state_is_to_parse(self):
        task = self._make_task()
        self.assertEqual(task.state, "to_parse")

    def test_task_defaults_to_synchronous_parse(self):
        task = self._make_task()
        self.assertTrue(task.synchronous_parse)

    def test_task_name_sequence_generated(self):
        task = self._make_task()
        self.assertTrue(task.name, "Task name should be auto-generated")
        self.assertNotEqual(task.name, "New")

    def test_task_default_company_is_env_company(self):
        task = self._make_task()
        self.assertEqual(task.company_id, self.env.company)

    def test_new_task_requires_statement(self):
        self.assertTrue(self._make_task().statement_required)

    def test_duplicate_source_pdf_is_rejected(self):
        source = self.env["ir.attachment"].create({
            "name": "duplicate.pdf",
            "datas": base64.b64encode(b"%PDF-duplicate"),
        })
        provider = self._make_provider()
        self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": provider.id,
        })
        with self.assertRaises(ValidationError):
            self.env["vendor.invoice.import.task"].create({
                "source_pdf_attachment_id": source.id,
                "selected_provider_config_id": provider.id,
            })

    def test_cancelled_statement_releases_business_key(self):
        admin = self.env.ref("base.user_admin")
        admin.write({
            "groups_id": [(4, self.env.ref("ai_vendor_invoice.group_reviewer").id)]
        })
        supplier = self.env.ref("base.res_partner_1")
        provider = self._make_provider()
        def make_task(suffix):
            source = self.env["ir.attachment"].create({
                "name": "%s.pdf" % suffix,
                "datas": base64.b64encode(suffix.encode()),
            })
            return self.env["vendor.invoice.import.task"].create({
                "source_pdf_attachment_id": source.id,
                "selected_provider_config_id": provider.id,
            }).with_user(admin)

        first = make_task("first")
        first_attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": first.id,
            "sequence": 1,
            "provider_config_id": provider.id,
            "status": "success",
        })
        first.current_parse_attempt_id = first_attempt.id
        payload = {
            "invoice_number": "CC06-001",
            "supplier_id": supplier.id,
            "lines": [{"description": "Freight", "amount": 10.0}],
        }
        first_statement = first.action_create_statement_from_attempt(
            first_attempt.id, payload
        )

        second = make_task("second")
        second_attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": second.id,
            "sequence": 1,
            "provider_config_id": provider.id,
            "status": "success",
        })
        second.current_parse_attempt_id = second_attempt.id
        with self.assertRaises(ValidationError):
            second.action_create_statement_from_attempt(second_attempt.id, payload)

        first.action_cancel_statement()
        second_statement = second.action_create_statement_from_attempt(
            second_attempt.id, payload
        )
        self.assertEqual(first_statement.state, "cancelled")
        self.assertEqual(second_statement.invoice_number, "CC06-001")

    def test_prefilled_statement_matches_supplier_case_insensitively(self):
        partner = self.env["res.partner"].create({
            "name": "UAT Mainfreight Forwarding Netherlands B.V.",
        })
        task = self._make_task()
        self.assertEqual(
            task._find_supplier_partner("UAT MAINFREIGHT FORWARDING NETHERLANDS B.V."),
            partner,
        )

    def test_supplier_partial_match_requires_unique_candidate(self):
        partner = self.env["res.partner"].create({
            "name": "UAT Unique Mainfreight Forwarding B.V.",
        })
        task = self._make_task()
        self.assertEqual(task._find_supplier_partner("UAT Unique Mainfreight"), partner)
        self.env["res.partner"].create({"name": "UAT Unique Mainfreight Logistics"})
        self.assertFalse(task._find_supplier_partner("UAT Unique Mainfreight"))

    def test_statement_generic_crud_is_not_a_business_entry_point(self):
        task = self._make_task()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {
                "task_id": task.id,
                "sequence": 1,
                "provider_config_id": task.selected_provider_config_id.id,
                "status": "success",
            }
        )
        values = {
            "task_id": task.id,
            "source_parse_attempt_id": attempt.id,
            "invoice_number": "INV-001",
        }
        with self.assertRaises(AccessError):
            self.env["vendor.invoice.statement"].create(values)

    def test_statement_first_creation_keeps_attempt_provenance(self):
        admin = self.env.ref("base.user_admin")
        admin.write({
            "groups_id": [(4, self.env.ref("ai_vendor_invoice.group_reviewer").id)]
        })
        task = self._make_task().with_user(admin)
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {
                "task_id": task.id,
                "sequence": 1,
                "provider_config_id": task.selected_provider_config_id.id,
                "status": "success",
            }
        )
        task.current_parse_attempt_id = attempt.id
        statement = task.action_create_statement_from_attempt(
            attempt.id,
            {"invoice_number": "INV-001", "lines": [{"description": "Freight", "amount": 10.0}]},
        )
        self.assertRegex(statement.name, r"^vendor/stm/\d{8}$")
        self.assertEqual(statement.source_parse_attempt_id, attempt)
        self.assertEqual(statement.state, "draft")
        self.assertEqual(task.statement_id, statement)
        self.assertEqual(len(statement.line_ids), 1)
        self.assertEqual(statement.line_ids.description, "Freight")

    def test_statement_line_amounts_recalculate_deterministically(self):
        admin = self.env.ref("base.user_admin")
        admin.write({
            "groups_id": [(4, self.env.ref("ai_vendor_invoice.group_reviewer").id)]
        })
        task = self._make_task().with_user(admin)
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": task.selected_provider_config_id.id,
            "status": "success",
        })
        statement = task.action_create_statement_from_attempt(
            attempt.id,
            {"invoice_number": "INV-AMOUNTS", "lines": [{
                "description": "Freight",
                "amount": 100.0,
                "tax_rate": 10.0,
            }]},
        )
        line = statement.line_ids
        self.assertEqual(line.tax_amount, 10.0)
        self.assertEqual(line.total_amount, 110.0)

        line.write({"tax_rate": 20.0})
        self.assertEqual(line.amount, 100.0)
        self.assertEqual(line.tax_amount, 20.0)
        self.assertEqual(line.total_amount, 120.0)
        line.write({"tax_amount": 5.0})
        self.assertEqual(line.tax_rate, 5.0)
        self.assertEqual(line.total_amount, 105.0)
        line.write({"total_amount": 130.0})
        self.assertEqual(line.tax_amount, 30.0)
        self.assertEqual(line.tax_rate, 30.0)
        line.write({"amount": 200.0})
        self.assertEqual(line.tax_amount, 60.0)
        self.assertEqual(line.total_amount, 260.0)

    def test_statement_line_onchange_updates_linked_amounts(self):
        admin = self.env.ref("base.user_admin")
        admin.write({
            "groups_id": [(4, self.env.ref("ai_vendor_invoice.group_reviewer").id)]
        })
        task = self._make_task().with_user(admin)
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": task.selected_provider_config_id.id,
            "status": "success",
        })
        statement = task.action_create_statement_from_attempt(
            attempt.id,
            {"invoice_number": "INV-ONCHANGE", "lines": [{
                "description": "Freight",
                "amount": 100.0,
                "tax_rate": 10.0,
            }]},
        )
        line = statement.line_ids
        line.tax_rate = 20.0
        line._onchange_tax_rate()
        self.assertEqual((line.amount, line.tax_amount, line.total_amount), (100.0, 20.0, 120.0))
        line.tax_amount = 5.0
        line._onchange_tax_amount()
        self.assertEqual((line.amount, line.tax_rate, line.total_amount), (100.0, 5.0, 105.0))
        line.total_amount = 130.0
        line._onchange_total_amount()
        self.assertEqual((line.amount, line.tax_amount, line.tax_rate), (100.0, 30.0, 30.0))

    def test_statement_line_rejects_nonzero_tax_on_zero_amount(self):
        admin = self.env.ref("base.user_admin")
        admin.write({
            "groups_id": [(4, self.env.ref("ai_vendor_invoice.group_reviewer").id)]
        })
        task = self._make_task().with_user(admin)
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": task.selected_provider_config_id.id,
            "status": "success",
        })
        statement = task.action_create_statement_from_attempt(
            attempt.id,
            {"invoice_number": "INV-ZERO", "lines": [{
                "description": "Zero",
                "amount": 0.0,
            }]},
        )
        with self.assertRaises(ValidationError):
            statement.line_ids.write({"amount": 0.0, "tax_amount": 1.0})
        self.assertEqual(statement.line_ids.tax_rate, 0.0)
        self.assertEqual(statement.line_ids.total_amount, 0.0)

    def test_statement_totals_and_non_draft_line_readonly(self):
        admin = self.env.ref("base.user_admin")
        admin.write({
            "groups_id": [(4, self.env.ref("ai_vendor_invoice.group_reviewer").id)]
        })
        task = self._make_task().with_user(admin)
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": task.selected_provider_config_id.id,
            "status": "success",
        })
        statement = task.action_create_statement_from_attempt(
            attempt.id,
            {"invoice_number": "INV-TOTALS", "lines": [{
                "description": "Freight",
                "amount": 100.0,
                "tax_rate": 10.0,
            }]},
        )
        self.assertEqual(statement.subtotal, 100.0)
        self.assertEqual(statement.total_tax, 10.0)
        self.assertEqual(statement.total_amount, 110.0)
        self.assertEqual(statement.overall_tax_rate, 10.0)
        task.action_cancel_statement()
        with self.assertRaises(ValidationError):
            statement.line_ids.write({"amount": 50.0})

    def test_statement_confirmation_projects_human_review_result(self):
        admin = self.env.ref("base.user_admin")
        admin.write({
            "groups_id": [(4, self.env.ref("ai_vendor_invoice.group_reviewer").id)]
        })
        task = self._make_task().with_user(admin)
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {
                "task_id": task.id,
                "sequence": 1,
                "provider_config_id": task.selected_provider_config_id.id,
                "status": "success",
            }
        )
        task.current_parse_attempt_id = attempt.id
        task.action_confirm_statement({
            "header": {
                "supplier_id": self.env.ref("base.res_partner_1").id,
                "invoice_number": "INV-002",
                "invoice_date": "2026-08-25",
                "currency_id": self.env.company.currency_id.id,
                "total_amount": "10.0",
                "total_tax": "0.0",
            },
            "lines": [{
                "description": "Freight",
                "quantity": "1",
                "unit_price": "10.0",
                "subtotal": "10.0",
                "tax_ids": [],
                "line_total_amount": "10.0",
            }],
        })
        self.assertEqual(task.state, "awaiting_review")
        self.assertEqual(task.statement_id.state, "confirmed")
        self.assertEqual(task.human_review_result["header"]["invoice_number"], "INV-002")
        self.assertEqual(task.human_review_result["header"]["supplier_id"],
                         self.env.ref("base.res_partner_1").id)
        self.assertEqual(task.human_review_result["statement_id"], task.statement_id.id)
        self.assertEqual(
            task.human_review_result["lines"][0]["statement_line_id"],
            task.statement_id.line_ids.id,
        )

    def test_statement_state_transition_commands_guard_direct_state_write(self):
        admin = self.env.ref("base.user_admin")
        admin.write({
            "groups_id": [(4, self.env.ref("ai_vendor_invoice.group_reviewer").id)]
        })
        task = self._make_task().with_user(admin)
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {
                "task_id": task.id,
                "sequence": 1,
                "provider_config_id": task.selected_provider_config_id.id,
                "status": "success",
            }
        )
        task.current_parse_attempt_id = attempt.id
        statement = task.action_create_statement_from_attempt(
            attempt.id,
            {"invoice_number": "INV-STATE", "lines": [{"description": "Freight", "amount": 10.0}]},
        )
        with self.assertRaises(AccessError):
            statement.write({"state": "confirmed"})
        task.action_cancel_statement()
        self.assertEqual(statement.state, "cancelled")
        with self.assertRaises(ValidationError):
            task.action_cancel_statement()

    def test_statement_projection_rejects_inconsistent_result(self):
        admin = self.env.ref("base.user_admin")
        admin.write({
            "groups_id": [(4, self.env.ref("ai_vendor_invoice.group_reviewer").id)]
        })
        task = self._make_task().with_user(admin)
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {
                "task_id": task.id,
                "sequence": 1,
                "provider_config_id": task.selected_provider_config_id.id,
                "status": "success",
            }
        )
        task.current_parse_attempt_id = attempt.id
        task.action_confirm_statement({
            "header": {
                "supplier_id": self.env.ref("base.res_partner_1").id,
                "invoice_number": "INV-003",
                "invoice_date": "2026-08-25",
                "currency_id": self.env.company.currency_id.id,
                "total_amount": "10.0",
                "total_tax": "0.0",
            },
            "lines": [],
        })
        from ..services.statement_projection import assert_projection_consistent

        inconsistent = dict(task.human_review_result)
        inconsistent["header"] = dict(inconsistent["header"], invoice_number="OLD")
        with self.assertRaises(ValidationError):
            assert_projection_consistent(task.statement_id, inconsistent)

    # ── T-025: company_id immutability ────────────────────────────────────────

    def test_task_company_id_immutable(self):
        """T-025: writing company_id after creation must raise ValidationError."""
        task = self._make_task()
        with self.assertRaises(ValidationError):
            task.write({"company_id": self.env.company.id})

    def test_cancelled_task_releases_pdf_checksum(self):
        provider = self._make_provider()
        pdf = base64.b64encode(b"%PDF-cc08-cancel")

        def make_task(name):
            attachment = self.env["ir.attachment"].create({
                "name": "%s.pdf" % name,
                "datas": pdf,
            })
            return self.env["vendor.invoice.import.task"].create({
                "source_pdf_attachment_id": attachment.id,
                "selected_provider_config_id": provider.id,
            })

        first = make_task("first")
        first.action_cancel_task()
        second = make_task("second")
        self.assertEqual(first.state, "cancelled")
        self.assertEqual(second.state, "to_parse")

    def test_cancel_task_marks_active_attempt_cancelled(self):
        task = self._make_task()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": task.selected_provider_config_id.id,
            "status": "running",
        })
        task.write({
            "current_parse_attempt_id": attempt.id,
            "state": "parsing",
        })

        task.action_cancel_task()

        self.assertEqual(task.state, "cancelled")
        self.assertEqual(attempt.status, "cancelled")

    def test_error_state_uses_error_badge(self):
        task = self._make_task()
        task.state = "error"
        self.assertEqual(task.parse_error_badge, "Error")
        task.state = "cancelled"
        self.assertFalse(task.parse_error_badge)

    # ── JSON field defaults ───────────────────────────────────────────────────

    def test_task_human_review_result_default_is_dict(self):
        task = self._make_task()
        self.assertEqual(task.human_review_result or {}, {})

    def test_task_review_warnings_default_is_list(self):
        task = self._make_task()
        self.assertEqual(task.review_warnings or [], [])

    def test_task_human_reviewed_default_is_false(self):
        task = self._make_task()
        self.assertFalse(task.human_reviewed)

    # ── next sequence helper ──────────────────────────────────────────────────

    def test_next_attempt_sequence_starts_at_one(self):
        task = self._make_task()
        self.assertEqual(task._get_next_attempt_sequence(), 1)

    def test_next_attempt_sequence_increments(self):
        task = self._make_task()
        provider = self._make_provider()
        self.env["vendor.invoice.import.parse.attempt"].create(
            {
                "task_id": task.id,
                "sequence": 1,
                "provider_config_id": provider.id,
                "status": "queued",
            }
        )
        self.assertEqual(task._get_next_attempt_sequence(), 2)

    # ── cron stub ─────────────────────────────────────────────────────────────

    def test_cron_check_parsing_timeout_is_callable(self):
        """Cron entry point must be callable without raising in Intent-1."""
        # Should return None (no-op stub)
        result = self.env["vendor.invoice.import.task"].cron_check_parsing_timeout()
        self.assertIsNone(result)


class TestParseAttemptModel(TransactionCase):
    """Tests for vendor.invoice.import.parse.attempt model."""

    def _make_base(self):
        att = self.env["ir.attachment"].create(
            {"name": "test.pdf", "datas": b"", "res_model": "vendor.invoice.import.task"}
        )
        provider = self.env["wd.ai.provider.config"].create(
            {"name": "P", "api_base_url": "https://x.com", "model_name": "m"}
        )
        task = self.env["vendor.invoice.import.task"].create(
            {
                "source_pdf_attachment_id": att.id,
                "selected_provider_config_id": provider.id,
            }
        )
        return task, provider

    # ── creation ──────────────────────────────────────────────────────────────

    def test_attempt_default_status_queued(self):
        task, provider = self._make_base()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {
                "task_id": task.id,
                "sequence": 1,
                "provider_config_id": provider.id,
            }
        )
        self.assertEqual(attempt.status, "queued")

    def test_attempt_default_retry_count_zero(self):
        task, provider = self._make_base()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {"task_id": task.id, "sequence": 1, "provider_config_id": provider.id}
        )
        self.assertEqual(attempt.attempt_internal_retry_count, 0)

    def test_attempt_submission_and_task_status_observability(self):
        task, provider = self._make_base()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {"task_id": task.id, "sequence": 1, "provider_config_id": provider.id}
        )
        self.assertTrue(attempt.submitted_at)
        task.current_parse_attempt_id = attempt.id
        self.assertEqual(task.parse_status, "queued")
        attempt.status = "running"
        attempt.started_at = fields.Datetime.now()
        self.assertEqual(task.parse_status, "running")
        attempt.write({
            "status": "failed",
            "error_summary": "The AI provider is temporarily unavailable. Please try again.",
        })
        self.assertEqual(task.parse_status, "failed")
        self.assertIn("temporarily unavailable", task.parse_error_summary)

    def test_duplicate_parse_submission_is_rejected(self):
        task, provider = self._make_base()
        from ..services import parse_service

        with patch.object(VendorInvoiceImportParseAttempt, "action_enqueue_parse"):
            parse_service.start_parse(self.env, task.id, provider.id)
        with self.assertRaises(ValueError):
            parse_service.start_parse(self.env, task.id, provider.id)

    def test_rerun_uses_task_parse_mode(self):
        task, provider = self._make_base()
        from ..services import parse_service

        with patch.object(parse_service, "start_parse", return_value=True) as start_parse:
            task.action_rerun_ai()
            start_parse.assert_called_once_with(
                self.env,
                task.id,
                provider.id,
                synchronous=True,
            )
            task.synchronous_parse = False
            task.action_rerun_ai()
            self.assertFalse(start_parse.call_args.kwargs["synchronous"])

    def test_synchronous_parse_uses_recordset_context(self):
        task, provider = self._make_base()
        from ..services import parse_service

        with patch.object(parse_service, "run_parse_attempt", return_value=True) as run:
            parse_service.start_parse(
                self.env,
                task.id,
                provider.id,
                synchronous=True,
            )
            self.assertTrue(run.call_args.args[0].context["ai_invoice_sync"])

    def test_queue_entry_requires_real_delay(self):
        task, provider = self._make_base()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {"task_id": task.id, "sequence": 1, "provider_config_id": provider.id}
        )
        with patch.dict("os.environ", {"QUEUE_JOB__NO_DELAY": "1"}):
            with self.assertRaises(UserError):
                attempt.action_enqueue_parse()

    def test_ai_parse_uses_dedicated_queue_channel(self):
        task, provider = self._make_base()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {"task_id": task.id, "sequence": 1, "provider_config_id": provider.id}
        )
        job = attempt.action_enqueue_parse()
        self.assertEqual(job.db_record().channel, "root.ai_invoice")

    def test_attempt_captures_extraction_contract_and_model_snapshot(self):
        task, provider = self._make_base()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {"task_id": task.id, "sequence": 1, "provider_config_id": provider.id}
        )
        provider.write({"model_name": "changed-after-attempt"})
        self.assertEqual(attempt.prompt_version, "vision-extraction-v1.3")
        self.assertEqual(
            attempt.extraction_contract_version,
            "transport-invoice-page-v1",
        )
        self.assertEqual(attempt.model_name_snapshot, "m")

    # ── T-018: unique(task_id, sequence) ─────────────────────────────────────

    def test_attempt_task_sequence_unique_constraint(self):
        """T-018: duplicate (task_id, sequence) must be rejected at DB level."""
        from psycopg2 import IntegrityError

        task, provider = self._make_base()
        self.env["vendor.invoice.import.parse.attempt"].create(
            {"task_id": task.id, "sequence": 1, "provider_config_id": provider.id}
        )
        with self.assertRaises(Exception):  # IntegrityError wrapped by Odoo
            self.env["vendor.invoice.import.parse.attempt"].create(
                {"task_id": task.id, "sequence": 1, "provider_config_id": provider.id}
            )
            self.env.cr.flush()

    # ── T-024: job_run_parse delegates to the Intent-2 parse service ─────────

    def test_job_run_parse_delegates_to_parse_service(self):
        task, provider = self._make_base()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {"task_id": task.id, "sequence": 1, "provider_config_id": provider.id}
        )
        with patch(
            "odoo.addons.ai_vendor_invoice.services.parse_service.run_parse_attempt",
            return_value=True,
        ) as run_parse:
            attempt.job_run_parse()
        run_parse.assert_called_once_with(self.env, task.id, attempt.id)

    # ── cascade delete ────────────────────────────────────────────────────────

    def test_attempt_cascade_deleted_with_task(self):
        task, provider = self._make_base()
        attempt = self.env["vendor.invoice.import.parse.attempt"].create(
            {"task_id": task.id, "sequence": 1, "provider_config_id": provider.id}
        )
        attempt_id = attempt.id
        task.unlink()
        self.assertFalse(
            self.env["vendor.invoice.import.parse.attempt"].browse(attempt_id).exists()
        )


class TestImportLogModel(TransactionCase):
    """Tests for vendor.invoice.import.log model."""

    def _make_task(self):
        att = self.env["ir.attachment"].create(
            {"name": "t.pdf", "datas": b"", "res_model": "vendor.invoice.import.task"}
        )
        provider = self.env["wd.ai.provider.config"].create(
            {"name": "P2", "api_base_url": "https://y.com", "model_name": "m2"}
        )
        return self.env["vendor.invoice.import.task"].create(
            {
                "source_pdf_attachment_id": att.id,
                "selected_provider_config_id": provider.id,
            }
        )

    def test_log_creation_with_required_fields(self):
        task = self._make_task()
        log = self.env["vendor.invoice.import.log"].create(
            {
                "task_id": task.id,
                "action": "ai_parse",
                "user_id": self.env.user.id,
            }
        )
        self.assertTrue(log.id)
        self.assertEqual(log.action, "ai_parse")

    def test_log_cascade_deleted_with_task(self):
        task = self._make_task()
        log = self.env["vendor.invoice.import.log"].create(
            {"task_id": task.id, "action": "ai_parse", "user_id": self.env.user.id}
        )
        log_id = log.id
        task.unlink()
        self.assertFalse(
            self.env["vendor.invoice.import.log"].browse(log_id).exists()
        )


class TestSystemConfig(TransactionCase):
    """Tests for wd.system.config model."""

    def test_get_config_returns_record(self):
        cfg = self.env["wd.system.config"].get_config()
        self.assertTrue(cfg.id)

    def test_task_timeout_is_timedelta(self):
        import datetime

        cfg = self.env["wd.system.config"].get_config()
        self.assertIsInstance(cfg.task_timeout, datetime.timedelta)
        self.assertGreater(cfg.task_timeout.total_seconds(), 0)


class TestLockServiceSignatures(TransactionCase):
    """Verify lock_service AbstractModel exposes the expected methods."""

    def test_lock_service_has_lock_task(self):
        svc = self.env["wd.lock.service"]
        self.assertTrue(hasattr(svc, "lock_task"), "lock_service must have lock_task()")

    def test_lock_service_has_lock_attempt(self):
        svc = self.env["wd.lock.service"]
        self.assertTrue(
            hasattr(svc, "lock_attempt"), "lock_service must have lock_attempt()"
        )


class TestJsonSchemas(TransactionCase):
    """Pure Python schema validation tests – no DB interaction needed."""

    # ── canonical ─────────────────────────────────────────────────────────────

    def test_canonical_valid_minimal(self):
        jsonschema.validate(_minimal_canonical(), CANONICAL_INVOICE_RESULT_SCHEMA)

    def test_canonical_valid_with_lines(self):
        data = _minimal_canonical()
        data["lines"] = [
            {
                "description": {"value": "Service A", "confidence": 0.95},
                "amount": {"value": "100.00", "confidence": 0.9},
                "tax_raw_text": {"value": "13%", "confidence": 0.8},
            }
        ]
        jsonschema.validate(data, CANONICAL_INVOICE_RESULT_SCHEMA)

    def test_canonical_missing_required_field_fails(self):
        data = _minimal_canonical()
        del data["header"]["invoice_number"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(data, CANONICAL_INVOICE_RESULT_SCHEMA)

    def test_canonical_extra_property_fails(self):
        data = _minimal_canonical()
        data["unexpected_key"] = "oops"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(data, CANONICAL_INVOICE_RESULT_SCHEMA)

    def test_canonical_confidence_out_of_range_fails(self):
        data = _minimal_canonical()
        data["header"]["invoice_number"]["confidence"] = 1.5
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(data, CANONICAL_INVOICE_RESULT_SCHEMA)

    def test_canonical_is_multi_invoice_true(self):
        data = _minimal_canonical(is_multi=True)
        jsonschema.validate(data, CANONICAL_INVOICE_RESULT_SCHEMA)

    # ── mapping ───────────────────────────────────────────────────────────────

    def test_mapping_valid_empty(self):
        jsonschema.validate({}, MAPPING_RESULT_SCHEMA)

    def test_mapping_valid_with_candidates(self):
        data = {
            "supplier_candidates": [
                {
                    "partner_id": 1,
                    "name": "ACME",
                    "match_score": 0.9,
                    "match_type": "alias",
                    "matched_rule_id": 5,
                }
            ],
            "product_candidates": [],
            "tax_candidates": [],
            "currency_candidates": [],
        }
        jsonschema.validate(data, MAPPING_RESULT_SCHEMA)

    # ── human review ──────────────────────────────────────────────────────────

    def test_human_review_valid_empty(self):
        jsonschema.validate({}, HUMAN_REVIEW_RESULT_SCHEMA)

    def test_human_review_valid_full(self):
        data = {
            "header": {
                "supplier_id": 10,
                "invoice_number": "INV-001",
                "invoice_date": "2024-01-15",
                "currency_id": 1,
                "total_amount": "1130.00",
                "total_tax": "130.00",
            },
            "lines": [
                {
                    "product_id": 5,
                    "description": "Consulting",
                    "quantity": "1",
                    "unit_price": "1000.00",
                    "subtotal": "1000.00",
                    "tax_ids": [1],
                    "tax_amount": "130.00",
                    "line_total_amount": "1130.00",
                }
            ],
        }
        jsonschema.validate(data, HUMAN_REVIEW_RESULT_SCHEMA)

    # ── warnings ──────────────────────────────────────────────────────────────

    def test_warnings_valid_empty_list(self):
        jsonschema.validate([], REVIEW_WARNINGS_SCHEMA)

    def test_warnings_valid_with_item(self):
        data = [{"code": "AMOUNT_MISMATCH", "message": "Total amount does not match"}]
        jsonschema.validate(data, REVIEW_WARNINGS_SCHEMA)

    def test_warnings_extra_field_fails(self):
        data = [{"code": "X", "message": "Y", "extra": "bad"}]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(data, REVIEW_WARNINGS_SCHEMA)
