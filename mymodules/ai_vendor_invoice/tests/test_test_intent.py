# © 2024 Wukong Digital. License LGPL-3.
"""Closure TEST-INTENT-AI-VENDOR-002 coverage."""

import base64
from io import BytesIO
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from PyPDF2 import PdfWriter
from psycopg2 import OperationalError
from reportlab.pdfgen import canvas

from odoo import api, fields, registry
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..adapters.base import (
    AIProviderPermanentError,
    AIProviderTemporaryError,
    BaseAIProviderAdapter,
)
from ..services import bill_creator, mapping_service, parse_service, pdf_preprocessor


def _canonical():
    field = {"value": None, "confidence": 0.0}
    return {
        "header": {
            "invoice_number": {"value": "INV-TEST", "confidence": 0.9},
            "invoice_date": {"value": "2026-08-21", "confidence": 0.9},
            "supplier_raw_text": {"value": "Test supplier", "confidence": 0.9},
            "currency_raw_text": {"value": "EUR", "confidence": 0.9},
            "total_amount": {"value": "10.00", "confidence": 0.9},
            "total_tax": field,
        },
        "lines": [],
        "is_multi_invoice": False,
    }


@tagged("-standard", "closure_concurrency")
class TestClosureConcurrency(TransactionCase):
    def _pdf(self):
        stream = BytesIO()
        document = canvas.Canvas(stream)
        document.drawString(72, 720, "Concurrency")
        document.save()
        return base64.b64encode(stream.getvalue())

    def _bill_task(self):
        with registry(self.env.cr.dbname).cursor() as cr:
            setup_env = api.Environment(cr, self.env.uid, {})
            company = setup_env.company
            product = setup_env["product.product"].search([], limit=1)
            setup_env["wd.system.config"].get_config().write({
                "default_product_id": product.id,
            })
            partner = setup_env["res.partner"].create({
                "name": "Concurrent supplier",
            })
            source = setup_env["ir.attachment"].create({
                "name": "concurrent.pdf",
                "datas": self._pdf(),
                "res_model": "vendor.invoice.import.task",
            })
            provider = setup_env["wd.ai.provider.config"].create({
                "name": "Concurrent provider",
                "api_base_url": "https://example.invalid",
                "model_name": "test",
            })
            task = setup_env["vendor.invoice.import.task"].create({
                "source_pdf_attachment_id": source.id,
                "selected_provider_config_id": provider.id,
                "company_id": company.id,
                "state": "awaiting_review",
                "human_reviewed": True,
                "human_review_result": {
                    "header": {
                        "supplier_id": partner.id,
                        "invoice_number": "CONCURRENT-1",
                        "invoice_date": "2026-08-21",
                        "currency_id": company.currency_id.id,
                        "total_amount": "10.00",
                    },
                    "lines": [],
                },
            })
            task_id = task.id
            cr.commit()
            return task_id

    def test_concurrent_bill_creation_has_one_winner(self):
        task_id = self._bill_task()
        registry_obj = registry(self.env.cr.dbname)
        first_ready = threading.Event()
        second_started = threading.Event()
        release_first = threading.Event()

        def first_transaction():
            with registry_obj.cursor() as cr:
                worker_env = api.Environment(cr, self.env.uid, {})
                try:
                    task = worker_env["wd.lock.service"].lock_task(task_id)
                    task = task.with_company(task.company_id)
                    first_ready.set()
                    bill_creator._create_locked(worker_env, task)
                    release_first.wait(timeout=10)
                    cr.commit()
                except Exception as error:
                    cr.rollback()
                    return ("error", type(error).__name__)
            return ("success", True)

        def second_transaction():
            if not first_ready.wait(timeout=10):
                return ("error", "first transaction did not start")
            second_started.set()
            with registry_obj.cursor() as cr:
                worker_env = api.Environment(cr, self.env.uid, {})
                try:
                    bill_creator.create_vendor_bill(worker_env, task_id)
                    cr.commit()
                    return ("success", True)
                except Exception as error:
                    cr.rollback()
                    return ("error", type(error).__name__)

        results = [None, None]
        first = threading.Thread(
            target=lambda: results.__setitem__(0, first_transaction()),
            daemon=True,
        )
        second = threading.Thread(
            target=lambda: results.__setitem__(1, second_transaction()),
            daemon=True,
        )
        first.start()
        self.assertTrue(first_ready.wait(timeout=10))
        second.start()
        self.assertTrue(second_started.wait(timeout=10))
        release_first.set()
        first.join(timeout=20)
        second.join(timeout=20)
        self.assertFalse(first.is_alive(), "first transaction did not finish")
        self.assertFalse(second.is_alive(), "second transaction did not finish")
        self.assertEqual(sum(result[0] == "success" for result in results), 1)
        self.assertEqual(sum(result[0] == "error" for result in results), 1)
        with registry(self.env.cr.dbname).cursor() as cr:
            check_env = api.Environment(cr, self.env.uid, {})
            self.assertEqual(
                check_env["account.move"].sudo().search_count([
                    ("ref", "=", "CONCURRENT-1"),
                ]),
                1,
            )


class TestClosureStaleWorker(TransactionCase):
    def test_stale_worker_only_supersedes_attempt(self):
        source = self.env["ir.attachment"].create({
            "name": "stale.pdf",
            "datas": base64.b64encode(b"%PDF-1.4"),
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Stale provider",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": provider.id,
            "state": "parsing",
        })
        old_attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": provider.id,
            "status": "queued",
        })
        current_attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 2,
            "provider_config_id": provider.id,
            "status": "running",
        })
        task.write({"current_parse_attempt_id": current_attempt.id})
        self.assertFalse(parse_service.run_parse_attempt(
            self.env, task.id, old_attempt.id
        ))
        self.assertEqual(old_attempt.status, "superseded")
        self.assertEqual(task.state, "parsing")
        self.assertEqual(task.current_parse_attempt_id, current_attempt)


class TestParseLifecycleConvergence(TransactionCase):
    def _parse_fixture(self):
        source = self.env["ir.attachment"].create({
            "name": "failure.pdf",
            "datas": base64.b64encode(b"%PDF-1.4"),
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Failure provider",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": provider.id,
            "state": "parsing",
        })
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": provider.id,
            "status": "queued",
        })
        task.write({"current_parse_attempt_id": attempt.id})
        return task, attempt, provider

    def test_provider_failure_converges_attempt_and_task(self):
        task, attempt, _provider = self._parse_fixture()
        adapter = Mock()
        adapter.parse_pdf.side_effect = AIProviderPermanentError("schema failure")
        with patch.object(parse_service, "_publish_attempt_running"), \
                patch.object(parse_service, "prepare_provider_input",
                              return_value={"type": "pages"}), \
                patch.object(parse_service, "adapter_for", return_value=adapter):
            self.assertFalse(parse_service.run_parse_attempt(
                self.env, task.id, attempt.id
            ))
        self.assertEqual(attempt.status, "failed")
        self.assertTrue(attempt.completed_at)
        self.assertTrue(attempt.finished_at)
        self.assertEqual(task.state, "error")

    def test_repeated_execution_of_terminal_attempt_is_idempotent(self):
        task, attempt, _provider = self._parse_fixture()
        attempt.write({
            "status": "failed",
            "completed_at": fields.Datetime.now(),
            "finished_at": fields.Datetime.now(),
        })
        task.write({"state": "error"})
        self.assertFalse(parse_service.run_parse_attempt(
            self.env, task.id, attempt.id
        ))
        self.assertEqual(attempt.status, "failed")
        self.assertEqual(task.state, "error")

    def test_serialization_failure_retries_terminal_write(self):
        source = self.env["ir.attachment"].create({
            "name": "failure-serialization.pdf",
            "datas": base64.b64encode(b"%PDF-1.4"),
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Serialization provider",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        with registry(self.env.cr.dbname).cursor() as setup_cr:
            setup_env = api.Environment(setup_cr, self.env.uid, {})
            source = setup_env["ir.attachment"].create({
                "name": source.name,
                "datas": source.datas,
                "res_model": "vendor.invoice.import.task",
            })
            provider = setup_env["wd.ai.provider.config"].create({
                "name": provider.name,
                "api_base_url": provider.api_base_url,
                "model_name": provider.model_name,
            })
            task = setup_env["vendor.invoice.import.task"].create({
                "source_pdf_attachment_id": source.id,
                "selected_provider_config_id": provider.id,
                "state": "parsing",
            })
            attempt = setup_env["vendor.invoice.import.parse.attempt"].create({
                "task_id": task.id,
                "sequence": 1,
                "provider_config_id": provider.id,
                "status": "queued",
            })
            task.write({"current_parse_attempt_id": attempt.id})
            setup_cr.commit()
        task = self.env["vendor.invoice.import.task"].browse(task.id)
        attempt = self.env["vendor.invoice.import.parse.attempt"].browse(attempt.id)
        original = parse_service._write_failed_attempt
        calls = []

        def fail_once(env, task_id, attempt_id, summary, failure_stage):
            if not calls:
                calls.append(True)
                raise OperationalError("serialization failure")
            return original(
                env,
                task_id,
                attempt_id,
                summary,
                failure_stage,
            )

        with patch.object(parse_service, "_write_failed_attempt", side_effect=fail_once), \
                patch.object(self.env.cr, "rollback"):
            parse_service._failed_attempt(
                self.env, task.id, attempt.id,
                AIProviderPermanentError("schema failure"),
            )
        with registry(self.env.cr.dbname).cursor() as check_cr:
            check_env = api.Environment(check_cr, self.env.uid, {})
            checked_attempt = check_env[
                "vendor.invoice.import.parse.attempt"
            ].browse(attempt.id)
            checked_task = check_env[
                "vendor.invoice.import.task"
            ].browse(task.id)
            self.assertEqual(checked_attempt.status, "failed")
            self.assertEqual(checked_task.state, "error")
        with registry(self.env.cr.dbname).cursor() as cleanup_cr:
            cleanup_env = api.Environment(cleanup_cr, self.env.uid, {})
            cleanup_env["vendor.invoice.import.task"].browse(task.id).unlink()
            cleanup_cr.commit()


class TestClosureMultiCompany(TransactionCase):
    def test_bill_uses_task_company_not_request_company(self):
        companies = self.env["res.company"].search([], limit=2)
        if len(companies) < 2:
            self.skipTest("The database has fewer than two companies.")
        task_company, request_company = companies[0], companies[1]
        if not self.env["account.journal"].search([
            ("company_id", "=", task_company.id),
            ("type", "=", "purchase"),
        ], limit=1):
            self.skipTest("Task company has no purchase journal.")
        product = self.env["product.product"].search([], limit=1)
        partner = self.env["res.partner"].create({"name": "Company supplier"})
        source = self.env["ir.attachment"].create({
            "name": "company.pdf",
            "datas": base64.b64encode(b"%PDF-1.4"),
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Company provider",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        self.env["wd.system.config"].get_config().write({
            "default_product_id": product.id,
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": provider.id,
            "company_id": task_company.id,
            "state": "awaiting_review",
            "human_reviewed": True,
            "human_review_result": {
                "header": {
                    "supplier_id": partner.id,
                    "invoice_number": "COMPANY-1",
                    "invoice_date": "2026-08-21",
                    "currency_id": task_company.currency_id.id,
                    "total_amount": "10.00",
                },
                "lines": [],
            },
        })
        request_env = self.env["vendor.invoice.import.task"].with_company(
            request_company
        ).env
        bill = bill_creator.create_vendor_bill(request_env, task.id)
        self.assertEqual(bill.company_id, task_company)


class TestClosureSecurity(TransactionCase):
    def _user(self, name, group):
        return self.env["res.users"].sudo().create({
            "name": name,
            "login": name.lower().replace(" ", "."),
            "email": "%s@example.invalid" % name.lower().replace(" ", "."),
            "groups_id": [(6, 0, [group.id])],
        })

    def test_provider_secret_is_not_exposed_by_rpc_field_metadata(self):
        user_group = self.env.ref("ai_vendor_invoice.group_ai_invoice_user")
        reviewer_group = self.env.ref("ai_vendor_invoice.group_reviewer")
        config_group = self.env.ref("ai_vendor_invoice.group_config_manager")
        users = (
            self._user("Closure User", user_group),
            self._user("Closure Reviewer", reviewer_group),
            self._user("Closure Config", config_group),
        )
        for user in users[:2]:
            self.assertNotIn(
                "api_key",
                self.env["wd.ai.provider.config"].with_user(user).fields_get(),
            )
        self.assertIn(
            "api_key",
            self.env["wd.ai.provider.config"].with_user(users[2]).fields_get(),
        )

    def test_raw_response_attachment_has_access_control(self):
        user = self._user(
            "Raw Response User",
            self.env.ref("ai_vendor_invoice.group_ai_invoice_user"),
        )
        attachment = self.env["ir.attachment"].sudo().create({
            "name": "raw-response.json",
            "datas": base64.b64encode(b'{"safe": true}'),
            "res_model": "vendor.invoice.import.parse.attempt",
            "public": False,
        })
        with self.assertRaises(AccessError):
            attachment.with_user(user).check_access_rule("read")


class TestClosureAdapterBehavior(TransactionCase):
    def _provider(self):
        return SimpleNamespace(
            api_base_url="https://example.invalid",
            http_timeout=1,
        )

    def test_temporary_error_retries_and_updates_counter(self):
        attempt = Mock()
        response = Mock(status_code=200, content=b"{}",)
        response.json.return_value = {}
        adapter = BaseAIProviderAdapter.__new__(
            type("ConcreteAdapter", (BaseAIProviderAdapter,), {
                "parse_pdf": lambda self, *args, **kwargs: None,
            })
        )
        with patch("requests.post", side_effect=[
            requests.ConnectionError("temporary"),
            response,
        ]) as request:
            body, raw = adapter._request(
                self._provider(), {}, max_attempt_retry=1, attempt_obj=attempt
            )
        self.assertEqual(body, {})
        self.assertEqual(raw, b"{}")
        self.assertEqual(request.call_count, 2)
        attempt.write.assert_called_once_with({
            "attempt_internal_retry_count": 1,
        })

    def test_permanent_http_error_is_not_retried(self):
        response = Mock(status_code=400, content=b"")
        adapter = BaseAIProviderAdapter.__new__(
            type("ConcreteAdapter", (BaseAIProviderAdapter,), {
                "parse_pdf": lambda self, *args, **kwargs: None,
            })
        )
        with patch("requests.post", return_value=response) as request:
            with self.assertRaises(AIProviderPermanentError):
                adapter._request(self._provider(), {}, max_attempt_retry=3)
        request.assert_called_once()

    def test_retry_exhaustion_raises_temporary_error(self):
        adapter = BaseAIProviderAdapter.__new__(
            type("ConcreteAdapter", (BaseAIProviderAdapter,), {
                "parse_pdf": lambda self, *args, **kwargs: None,
            })
        )
        with patch("requests.post", side_effect=requests.Timeout("timeout")):
            with self.assertRaises(AIProviderTemporaryError):
                adapter._request(self._provider(), {}, max_attempt_retry=1)


class TestClosurePipeline(TransactionCase):
    def test_pdf_provider_input_adapter_mapping_pipeline(self):
        stream = BytesIO()
        document = canvas.Canvas(stream)
        document.drawString(72, 720, "Pipeline page 1")
        document.showPage()
        document.drawString(72, 720, "Pipeline page 2")
        document.save()
        source = self.env["ir.attachment"].create({
            "name": "pipeline.pdf",
            "datas": base64.b64encode(stream.getvalue()),
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Pipeline DeepSeek",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": provider.id,
            "state": "parsing",
        })
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": provider.id,
            "status": "queued",
        })
        task.write({"current_parse_attempt_id": attempt.id})
        adapter = Mock()
        adapter.parse_pdf.return_value = (
            _canonical(),
            base64.b64encode(b'{"canonical": true}'),
        )
        def publish_running(env, current_attempt):
            current_attempt.write({
                "status": "running",
                "started_at": fields.Datetime.now(),
            })
        with patch("odoo.addons.ai_vendor_invoice.services.parse_service.adapter_for",
                   return_value=adapter), \
                patch.object(parse_service, "_publish_attempt_running",
                              side_effect=publish_running):
            self.assertTrue(parse_service.run_parse_attempt(
                self.env, task.id, attempt.id
            ))
        provider_input = adapter.parse_pdf.call_args.args[0]
        self.assertEqual(provider_input["type"], "pages")
        self.assertEqual(len(provider_input["images"]), 2)
        self.assertEqual(task.state, "awaiting_review")
        self.assertFalse(hasattr(task, "page_images"))
        self.assertFalse(hasattr(attempt, "page_images"))
        self.assertTrue(attempt.mapping_result is not None)
        self.assertEqual(attempt.raw_response_attachment_id.res_model, attempt._name)
        self.assertFalse(attempt.raw_response_attachment_id.public)


class TestClosurePDFErrors(TransactionCase):
    def test_render_failure_is_distinguishable(self):
        attachment = SimpleNamespace(raw=b"%PDF-1.4")
        fake_page = Mock()
        fake_page.get_pixmap.side_effect = RuntimeError("render")
        fake_document = Mock(page_count=1, needs_pass=False)
        fake_document.load_page.return_value = fake_page
        with patch.object(
            pdf_preprocessor.fitz,
            "open",
            return_value=fake_document,
        ):
            with self.assertRaises(pdf_preprocessor.PDFRenderError):
                pdf_preprocessor.prepare_provider_input(attachment)
