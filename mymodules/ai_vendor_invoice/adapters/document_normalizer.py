# © 2024 Wukong Digital. License LGPL-3.
import copy
import re

from jsonschema import ValidationError, validate

from .base import AIProviderPermanentError, BaseAIProviderAdapter
from ..schemas.canonical import CANONICAL_INVOICE_RESULT_SCHEMA
from ..schemas.page_extraction import PAGE_EXTRACTION_RESULT_SCHEMA


class DocumentNormalizationError(AIProviderPermanentError):
    """Page results cannot be converted into one canonical invoice."""

    def __init__(self, message, diagnostic=None):
        super().__init__(message)
        self.diagnostic = diagnostic or {}


_HEADER_ALIASES = {
    "invoice_number": {"invoice_number", "invoice_no", "invoicenumber", "factuurnummer"},
    "invoice_date": {"invoice_date", "invoicedate", "factuurdatum"},
    "supplier_raw_text": {"supplier", "supplier_name", "supplier_raw_text", "leverancier"},
    "currency_raw_text": {"currency", "currency_raw_text", "valuta"},
    "total_amount": {"total", "total_amount", "totalamount", "totaal", "totaalbedrag"},
    "total_tax": {"tax", "total_tax", "totaltax", "btw", "btwbedrag"},
}


def _key(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _value_key(value):
    return str(value).strip()


def _semantic_values(values):
    result = {}
    for field, value in values.items():
        normalized = _key(field)
        for canonical, aliases in _HEADER_ALIASES.items():
            if normalized in {_key(alias) for alias in aliases}:
                result[canonical] = value
                break
    return result


def _header_candidates(page_result):
    candidates = []
    for field, value in _semantic_values(
        page_result.get("header", {})
    ).items():
        candidates.append((field, value, 3, "header"))
    return candidates


def _select_header_values(ordered, skip_fields=None):
    skip_fields = skip_fields or set()
    candidates_by_field = {}
    for page_result in ordered:
        candidates = _header_candidates(page_result)
        for field, value, source_weight, source_label in candidates:
            if field in skip_fields:
                continue
            if value in (None, ""):
                continue
            candidates_by_field.setdefault(field, []).append({
                "page": page_result["page_number"],
                "value": value,
                "source_label": source_label,
                "score": source_weight * 1000 + len(candidates),
            })

    selected = {}
    for field, candidates in candidates_by_field.items():
        unique_values = {}
        for candidate in candidates:
            unique_values.setdefault(_value_key(candidate["value"]), []).append(candidate)
        if len(unique_values) == 1:
            selected[field] = candidates[0]["value"]
            continue
        for value_candidates in unique_values.values():
            frequency = len(value_candidates)
            for candidate in value_candidates:
                candidate["score"] += frequency * 10
        best_score = max(candidate["score"] for candidate in candidates)
        best = [candidate for candidate in candidates
                if candidate["score"] == best_score]
        best_values = {_value_key(candidate["value"]) for candidate in best}
        if len(best_values) != 1:
            raise DocumentNormalizationError(
                "Document normalization produced an invalid canonical result.",
                {
                    "code": "HEADER_CONFLICT",
                    "field": field,
                    "candidate_count": len(unique_values),
                    "pages": sorted({candidate["page"] for candidate in best}),
                },
            )
        selected[field] = best[0]["value"]
    return selected


def _validate_page_result(page_result):
    """Validate model fields while retaining Python-added raw-fact provenance."""
    if not isinstance(page_result, dict):
        raise TypeError("Page extraction must be an object.")
    model_result = copy.deepcopy(page_result)
    for fact in model_result.get("raw_facts", []):
        fact.pop("source_page", None)
    for line in model_result.get("lines", []):
        for fact in line.get("raw_fields", []):
            fact.pop("source_page", None)
    validate(model_result, PAGE_EXTRACTION_RESULT_SCHEMA)
    page_number = model_result["page_number"]
    for fact in page_result.get("raw_facts", []):
        if "source_page" not in fact:
            fact["source_page"] = page_number
        elif fact["source_page"] != page_number:
            raise ValueError("Raw fact source page does not match its page.")
    for line in page_result.get("lines", []):
        for fact in line.get("raw_fields", []):
            if "source_page" not in fact:
                fact["source_page"] = page_number
            elif fact["source_page"] != page_number:
                raise ValueError("Raw field source page does not match its page.")


def normalize_page_results(page_results):
    try:
        page_results = copy.deepcopy(page_results)
        for page_result in page_results:
            _validate_page_result(page_result)
        if not page_results:
            raise ValueError("No page extraction results were returned.")

        ordered = sorted(page_results, key=lambda result: result["page_number"])
        lines = []
        for page_result in ordered:
            lines.extend(page_result.get("lines", []))

        invoice_values_by_page = {}
        for page_result in ordered:
            values = {
                _value_key(value)
                for field, value, _weight, _source in _header_candidates(page_result)
                if field == "invoice_number" and value not in (None, "")
            }
            if values:
                invoice_values_by_page[page_result["page_number"]] = values
        explicit_invoice_values = {
            value for values in invoice_values_by_page.values() for value in values
        }
        multi_invoice = (
            len(invoice_values_by_page) > 1
            and len(explicit_invoice_values) > 1
        )
        header_values = _select_header_values(
            ordered,
            {"invoice_number"} if multi_invoice else None,
        )
        if multi_invoice:
            header_values["invoice_number"] = None

        fields = (
            "invoice_number", "invoice_date", "supplier_raw_text",
            "currency_raw_text", "total_amount", "total_tax",
        )
        header = {
            field: {"value": header_values.get(field), "confidence": 0.0}
            for field in fields
        }
        canonical_lines = []
        for line in lines:
            normalized = {_key(field): value for field, value in line.items()}
            canonical_lines.append({
                "description": {
                    "value": next(
                        (normalized[key] for key in ("description", "omschrijving",
                                                     "aantalunitomschrijving")
                         if key in normalized), None
                    ),
                    "confidence": 0.0,
                },
                "amount": {
                    "value": next(
                        (normalized[key] for key in ("amount", "bedrag", "kosten",
                                                     "subtotal", "totaal")
                         if key in normalized), None
                    ),
                    "confidence": 0.0,
                },
                "tax_raw_text": {
                    "value": next(
                        (normalized[key] for key in ("tax", "taxrawtext", "btw")
                         if key in normalized), None
                    ),
                    "confidence": 0.0,
                },
            })
        result = {
            "header": header,
            "lines": canonical_lines,
            "is_multi_invoice": multi_invoice,
        }
        result = BaseAIProviderAdapter._canonical(result)
        validate(result, CANONICAL_INVOICE_RESULT_SCHEMA)
        return result
    except (ValidationError, TypeError, ValueError, AIProviderPermanentError) as error:
        if isinstance(error, DocumentNormalizationError):
            raise
        raise DocumentNormalizationError(
            "Document normalization produced an invalid canonical result."
        ) from error
