# © 2024 Wukong Digital. License LGPL-3.
"""Regression tests for FIX-INTENT-AI-VENDOR-001."""

from datetime import date
from decimal import Decimal
from io import BytesIO
import base64
import inspect
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyPDF2 import PdfWriter
from reportlab.pdfgen import canvas
from jsonschema import ValidationError
from odoo.tests.common import TransactionCase

from ..adapters.base import AIProviderPermanentError, BaseAIProviderAdapter
from ..adapters.deepseek import DeepSeekAIProviderAdapter
from ..adapters.deepseek import (
    EXTRACTION_CONTRACT_VERSION,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    USER_PROMPT,
)
from ..schemas.page_extraction import PAGE_EXTRACTION_RESULT_SCHEMA
from ..adapters.document_normalizer import (
    DocumentNormalizationError,
    normalize_page_results,
)
from ..models.import_parse_attempt import VendorInvoiceImportParseAttempt
from ..services import parse_service, pdf_preprocessor


def _canonical_result():
    field = {"value": None, "confidence": 0.0}
    return {
        "header": {
            "invoice_number": {"value": " INV-001 ", "confidence": 0.8},
            "invoice_date": {"value": date(2026, 8, 21), "confidence": 0.8},
            "supplier_raw_text": {"value": " Supplier ", "confidence": 0.8},
            "currency_raw_text": {"value": " EUR ", "confidence": 0.8},
            "total_amount": {"value": Decimal("10.00"), "confidence": 0.8},
            "total_tax": field,
        },
        "lines": [],
        "is_multi_invoice": False,
    }


class FixIntentBase(TransactionCase):
    def _base_task(self, state="awaiting_review"):
        attachment = self.env["ir.attachment"].create({
            "name": "fix-intent.pdf",
            "datas": b"",
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "DeepSeek Fix Intent",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
            "max_internal_retry": 3,
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": attachment.id,
            "selected_provider_config_id": provider.id,
            "state": state,
        })
        return task, provider


class TestFixIntentParse(FixIntentBase):
    def test_rerun_preserves_human_review_result(self):
        task, provider = self._base_task()
        original = {
            "header": {
                "supplier_id": 7,
                "invoice_number": "INV-001",
                "invoice_date": "2026-08-21",
                "currency_id": 1,
                "total_amount": "10.00",
            },
            "lines": [],
        }
        task.write({
            "human_review_result": original,
            "human_reviewed": True,
        })
        with patch.object(VendorInvoiceImportParseAttempt, "action_enqueue_parse"):
            parse_service.start_parse(self.env, task.id, provider.id)
        self.assertEqual(task.human_review_result, original)
        self.assertFalse(task.human_reviewed)


class TestFixIntentAdapter(TransactionCase):
    def test_final_request_has_frozen_contract_shape_and_options(self):
        adapter = DeepSeekAIProviderAdapter.__new__(DeepSeekAIProviderAdapter)
        provider = SimpleNamespace(
            api_base_url="https://example.invalid",
            http_timeout=1,
            model_name="deepseek-reasoner",
        )
        response = Mock()
        response.model_dump.return_value = {
            "choices": [{"message": {"content": '{"pages": [{"page_number": 1, "header": {}, "lines": []}]}'}}],
        }
        response.model_dump_json.return_value = "{}"
        client = Mock()
        client.chat.completions.create.return_value = response

        adapter._parse_page_batch(client, provider, [b"png"], 0, None, 0, 1)
        payload = client.chat.completions.create.call_args.kwargs
        self.assertEqual(payload["model"], provider.model_name)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["extra_body"], {"thinking": {"type": "enabled"}})
        self.assertFalse(payload["stream"])
        self.assertEqual([message["role"] for message in payload["messages"]],
                         ["system", "user"])
        self.assertEqual(len(payload["messages"][1]["content"]), 2)
        self.assertEqual(payload["messages"][1]["content"][0]["type"], "text")
        self.assertEqual(payload["messages"][1]["content"][1]["type"], "image_url")

    def test_adapter_rejects_invalid_canonical_schema(self):
        invalid = _canonical_result()
        invalid["header"].pop("invoice_number")
        with self.assertRaises(AIProviderPermanentError):
            BaseAIProviderAdapter._canonical(invalid)
        with self.assertRaises(AIProviderPermanentError):
            BaseAIProviderAdapter._canonical([])

    def test_adapter_normalizes_valid_canonical_values(self):
        result = BaseAIProviderAdapter._canonical({
            "canonical_result": _canonical_result(),
        })
        self.assertEqual(result["header"]["invoice_number"]["value"], "INV-001")
        self.assertEqual(result["header"]["invoice_date"]["value"], "2026-08-21")
        self.assertEqual(result["header"]["total_amount"]["value"], "10.00")

    def test_adapter_accepts_provider_input_not_attachment(self):
        signature = inspect.signature(DeepSeekAIProviderAdapter.parse_pdf)
        self.assertEqual(list(signature.parameters)[1], "provider_input")

    def test_openai_sdk_automatic_retries_are_disabled(self):
        adapter = DeepSeekAIProviderAdapter.__new__(DeepSeekAIProviderAdapter)
        provider = SimpleNamespace(
            api_base_url="https://example.invalid",
            http_timeout=1,
            model_name="test",
        )
        with patch.object(adapter, "_credentials", return_value="configured"):
            with patch(
                "odoo.addons.ai_vendor_invoice.adapters.deepseek.OpenAI"
            ) as openai:
                with patch.object(
                    adapter,
                    "_parse_page_batch",
                    return_value=({"page_number": 1, "lines": []}, "{}"),
                ):
                    adapter.parse_pdf({"images": [b"png"]}, provider)
        self.assertEqual(openai.call_args.kwargs["max_retries"], 0)

    def test_page_extraction_allows_missing_document_headers(self):
        result = normalize_page_results([{
            "page_number": 1,
            "lines": [],
        }])
        self.assertIsNone(result["header"]["invoice_number"]["value"])
        self.assertEqual(result["lines"], [])

    def test_page_extraction_accepts_scalar_headers_and_lines(self):
        result = DeepSeekAIProviderAdapter._page_extraction({
            "header": {
                "invoice_number": "INV-001",
                "invoice_date": "2026-08-21",
                "total_amount": 10.5,
            },
            "lines": [{"description": "Freight", "amount": 10, "tax": None}],
        }, 1)
        self.assertEqual(result["header"]["total_amount"], 10.5)
        self.assertEqual(result["lines"][0]["amount"], 10)

    def test_document_normalization_detects_cross_page_invoice_numbers(self):
        pages = [
            {"page_number": 1, "header": {"invoice_number": "INV-001"}},
            {"page_number": 2, "header": {"invoice_number": "INV-002"}},
        ]
        result = normalize_page_results(pages)
        self.assertTrue(result["is_multi_invoice"])
        self.assertIsNone(result["header"]["invoice_number"]["value"])

    def test_document_normalization_accepts_repeated_invoice_number(self):
        result = normalize_page_results([
            {"page_number": 1, "header": {"invoice_number": "INV-001"}},
            {"page_number": 2, "header": {"invoice_number": "INV-001"}},
        ])
        self.assertEqual(result["header"]["invoice_number"]["value"], "INV-001")

    def test_header_value_wins_over_detail_reference(self):
        result = normalize_page_results([
            {"page_number": 1, "header": {"invoice_number": "INV-001"}},
            {"page_number": 2, "raw_facts": [{
                "source_label": "Shipment Number",
                "source_value": "SHIP-002",
                "source_page": 2,
            }]},
        ])
        self.assertEqual(result["header"]["invoice_number"]["value"], "INV-001")

    def test_cross_page_invoice_numbers_are_not_reported_as_header_conflict(self):
        result = normalize_page_results([
            {"page_number": 1, "header": {"invoice_number": "INV-001"}},
            {"page_number": 2, "header": {"invoice_number": "INV-002"}},
        ])
        self.assertTrue(result["is_multi_invoice"])

    def test_single_header_page_is_sufficient(self):
        result = normalize_page_results([
            {"page_number": 1, "header": {"invoice_number": "INV-001"}},
            {"page_number": 2, "lines": [{"description": "Freight"}]},
        ])
        self.assertEqual(result["header"]["invoice_number"]["value"], "INV-001")

    def test_detail_factuurnummer_does_not_override_header(self):
        result = normalize_page_results([
            {"page_number": 1, "header": {"invoice_number": "INV-001"}},
            {"page_number": 2, "raw_facts": [{
                "source_label": "Factuurnummer",
                "source_value": "SHIP-002",
                "source_page": 2,
            }], "lines": [{"description": "Shipment"}]},
        ])
        self.assertEqual(result["header"]["invoice_number"]["value"], "INV-001")

    def test_repeated_currency_and_total_are_accepted(self):
        result = normalize_page_results([
            {"page_number": 1, "header": {"currency": "EUR", "total": "10.00"}},
            {"page_number": 2, "header": {"currency": "EUR", "total": "10.00"}},
        ])
        self.assertEqual(result["header"]["currency_raw_text"]["value"], "EUR")
        self.assertEqual(result["header"]["total_amount"]["value"], "10.00")

    def test_conflicting_total_is_not_silently_overwritten(self):
        with self.assertRaises(DocumentNormalizationError) as error:
            normalize_page_results([
                {"page_number": 1, "header": {"total": "10.00"}},
                {"page_number": 2, "header": {"total": "11.00"}},
            ])
        self.assertEqual(error.exception.diagnostic["field"], "total_amount")

    def test_diagnostic_is_persisted_without_sensitive_payload(self):
        attachment = self.env["ir.attachment"].create({
            "name": "diagnostic.pdf",
            "datas": b"",
            "res_model": "vendor.invoice.import.task",
        })
        provider = self.env["wd.ai.provider.config"].create({
            "name": "Diagnostic DeepSeek",
            "api_base_url": "https://example.invalid",
            "model_name": "test",
        })
        task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": attachment.id,
            "selected_provider_config_id": provider.id,
        })
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": provider.id,
        })
        DeepSeekAIProviderAdapter._log_diagnostic(
            attempt, 1, 3, 1, 128, 55, 0, 200, None,
            "NONE", "PASS", "PASS", "2026-08-26T01:00:00+00:00",
        )
        diagnostic = attempt.provider_diagnostics[0]
        self.assertEqual(diagnostic["page_start"], 2)
        self.assertEqual(diagnostic["page_end"], 2)
        self.assertEqual(diagnostic["total_pages"], 3)
        self.assertEqual(diagnostic["response_parse_status"], "PASS")
        self.assertNotIn("prompt", diagnostic)
        self.assertNotIn("response", diagnostic)
        self.assertNotIn("api_key", diagnostic)

    def test_status_categories_match_fixed_transport_policy(self):
        self.assertEqual(
            DeepSeekAIProviderAdapter._status_category(408),
            "TEMPORARY_TIMEOUT",
        )
        self.assertEqual(
            DeepSeekAIProviderAdapter._status_category(429),
            "TEMPORARY_RATE_LIMIT",
        )
        self.assertEqual(
            DeepSeekAIProviderAdapter._status_category(503),
            "TEMPORARY_5XX",
        )
        self.assertEqual(
            DeepSeekAIProviderAdapter._status_category(413),
            "PERMANENT_UNSUPPORTED_INPUT",
        )
        self.assertEqual(
            DeepSeekAIProviderAdapter._status_category(422),
            "PERMANENT_BAD_REQUEST",
        )

    def test_document_normalization_preserves_page_order(self):
        first_line = {
            "description": "Freight",
            "amount": "10.00",
            "tax_raw_text": "0.00",
        }
        second_line = {
            "description": "Handling",
            "amount": "2.00",
            "tax_raw_text": "0.00",
        }
        merged = normalize_page_results([
            {"page_number": 1, "lines": [first_line]},
            {"page_number": 2, "lines": [second_line]},
        ])
        self.assertEqual(
            [line["description"]["value"] for line in merged["lines"]],
            ["Freight", "Handling"],
        )

    def test_document_normalization_rejects_identity_conflicts(self):
        first = {"page_number": 1, "header": {"invoice_number": "INV-001"}}
        conflicting_header = {
            "page_number": 2, "header": {"invoice_number": "INV-002"}
        }
        result = normalize_page_results([first, conflicting_header])
        self.assertTrue(result["is_multi_invoice"])

    def test_page_extraction_contract_and_local_raw_fact_provenance(self):
        body = {
            "header": {"invoice_number": "INV-001"},
            "raw_facts": [{
                "source_label": "Shipment Number",
                "source_value": "SHIP-002",
            }],
            "lines": [{
                "description": "Freight",
                "raw_fields": [{
                    "source_label": "Uw ref.",
                    "source_value": "REF-003",
                }],
            }],
        }
        result = DeepSeekAIProviderAdapter._page_extraction(body, 3)
        self.assertEqual(result["page_number"], 3)
        self.assertEqual(result["raw_facts"][0]["source_page"], 3)
        self.assertEqual(result["lines"][0]["raw_fields"][0]["source_page"], 3)

    def test_page_extraction_requires_raw_fact_labels_and_values(self):
        with self.assertRaises(ValidationError):
            DeepSeekAIProviderAdapter._page_extraction(
                {"raw_facts": [{"source_label": "Shipment Number"}]}, 1
            )
        with self.assertRaises(ValidationError):
            DeepSeekAIProviderAdapter._page_extraction(
                {"lines": [{"raw_fields": [{"source_value": "REF"}]}]}, 1
            )

    def test_page_extraction_rejects_model_provenance_and_document_fields(self):
        with self.assertRaises(ValidationError):
            DeepSeekAIProviderAdapter._page_extraction(
                {"raw_facts": [{
                    "source_label": "x", "source_value": "y", "source_page": 9,
                }]},
                1,
            )
        for field in ("is_multi_invoice", "references", "addresses"):
            with self.assertRaises(ValidationError):
                DeepSeekAIProviderAdapter._page_extraction({field: []}, 1)

    def test_page_extraction_rejects_removed_page_multi_invoice_flag(self):
        with self.assertRaises(ValidationError):
            DeepSeekAIProviderAdapter._page_extraction(
                {"is_multi_invoice": True}, 1
            )

    def test_prompts_and_versions_match_extraction_contract(self):
        self.assertEqual(EXTRACTION_CONTRACT_VERSION, "transport-invoice-page-v1")
        self.assertEqual(PROMPT_VERSION, "vision-extraction-v1.3")
        self.assertIn("not a business decision maker", SYSTEM_PROMPT)
        self.assertIn("raw_facts", SYSTEM_PROMPT)
        for clause in ("Do not guess", "autocomplete", "calculate",
                       "another page", "Shipment Number", "Dossier",
                       "O.No.", "Opdracht", "Uw ref.", "Your reference"):
            self.assertIn(clause, SYSTEM_PROMPT)
        for clause in ("fee or charge lines", "dates", "addresses", "raw_facts"):
            self.assertIn(clause, USER_PROMPT)
        self.assertNotIn("is_multi_invoice", USER_PROMPT)

    def test_prompt_explicitly_matches_page_extraction_schema(self):
        allowed = set(PAGE_EXTRACTION_RESULT_SCHEMA["properties"])
        self.assertIn("PageExtractionResult", SYSTEM_PROMPT)
        self.assertIn("PageExtractionResult", USER_PROMPT)
        self.assertIn("only these keys", SYSTEM_PROMPT)
        self.assertIn("Do not add any other top-level keys", SYSTEM_PROMPT)
        for key in allowed:
            self.assertIn(key, SYSTEM_PROMPT)
            self.assertIn(key, USER_PROMPT)
        self.assertIn("source_label", SYSTEM_PROMPT)
        self.assertIn("source_value", SYSTEM_PROMPT)
        self.assertNotIn('"sender"', SYSTEM_PROMPT)
        self.assertNotIn('"invoice_header"', SYSTEM_PROMPT)

    def test_normalizer_preserves_page_and_line_order_and_duplicate_lines(self):
        result = normalize_page_results([
            {"page_number": 2, "lines": [
                {"description": "same", "amount": "1", "raw_fields": [
                    {"source_label": "Uw ref.", "source_value": "R2",
                     "source_page": 2},
                ]},
            ], "raw_facts": [{"source_label": "note", "source_value": "p2",
                              "source_page": 2}]},
            {"page_number": 1, "lines": [
                {"description": "same", "amount": "1"},
            ]},
        ])
        self.assertEqual([line["description"]["value"] for line in result["lines"]],
                         ["same", "same"])
        self.assertEqual(result["is_multi_invoice"], False)

    def test_uncertain_references_and_raw_facts_do_not_trigger_multi_invoice(self):
        result = normalize_page_results([
            {"page_number": 1, "header": {"invoice_number": "INV-001"},
             "raw_facts": [{"source_label": "Dossier", "source_value": "INV-002"}]},
            {"page_number": 2, "raw_facts": [
                {"source_label": "Your reference", "source_value": "INV-003"},
            ], "lines": [{"description": "Shipment INV-004"}]},
        ])
        self.assertFalse(result["is_multi_invoice"])
        self.assertEqual(result["header"]["invoice_number"]["value"], "INV-001")

    def test_invoice_number_lexical_aliases_are_deterministic(self):
        result = normalize_page_results([
            {"page_number": 1, "header": {"Factuurnummer": "INV-001"}},
            {"page_number": 2, "header": {"Invoice Number": "INV-001"}},
        ])
        self.assertEqual(result["header"]["invoice_number"]["value"], "INV-001")


class TestFixIntentPDFPreprocessor(TransactionCase):
    @staticmethod
    def _pdf(page_count):
        output = BytesIO()
        document = canvas.Canvas(output)
        for page_number in range(page_count):
            document.drawString(72, 720, "Page %s" % (page_number + 1))
            document.showPage()
        document.save()
        return output.getvalue()

    def _attachment(self, contents):
        return self.env["ir.attachment"].create({
            "name": "preprocessor.pdf",
            "datas": base64.b64encode(contents),
            "res_model": "vendor.invoice.import.task",
        })

    def test_single_page_pdf_returns_pages_provider_input(self):
        result = pdf_preprocessor.prepare_provider_input(
            self._attachment(self._pdf(1))
        )
        self.assertEqual(result["type"], "pages")
        self.assertEqual(len(result["images"]), 1)
        self.assertTrue(result["images"][0].startswith(b"\x89PNG"))

    def test_multi_page_pdf_preserves_page_order(self):
        result = pdf_preprocessor.prepare_provider_input(
            self._attachment(self._pdf(2))
        )
        self.assertEqual(len(result["images"]), 2)
        self.assertNotEqual(result["images"][0], result["images"][1])

    def test_invalid_and_empty_pdf_are_distinguishable(self):
        with self.assertRaises(pdf_preprocessor.PDFInvalidError):
            pdf_preprocessor.prepare_provider_input(self._attachment(b"not-pdf"))
        with self.assertRaises(pdf_preprocessor.PDFInvalidError):
            pdf_preprocessor.prepare_provider_input(self._attachment(b""))

    def test_encrypted_pdf_is_distinguishable(self):
        output = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secret")
        writer.write(output)
        with self.assertRaises(pdf_preprocessor.PDFEncryptedError):
            pdf_preprocessor.prepare_provider_input(self._attachment(output.getvalue()))


class TestFixIntentReviewWarnings(FixIntentBase):
    def test_save_review_recomputes_review_warnings(self):
        reviewer = self.env.ref("ai_vendor_invoice.group_reviewer")
        self.env.user.sudo().write({"groups_id": [(4, reviewer.id)]})
        task, _provider = self._base_task()
        task.write({
            "human_reviewed": False,
            "review_warnings": [{"code": "OLD", "message": "old"}],
        })
        review = {
            "header": {"total_amount": "10.00"},
            "lines": [{
                "subtotal": "9.00",
                "tax_amount": "0.00",
                "line_total_amount": "9.00",
            }],
        }
        task.action_save_review(review)
        self.assertTrue(task.human_reviewed)
        self.assertEqual(task.review_warnings[0]["code"], "AMOUNT_MISMATCH")
