# © 2024 Wukong Digital. License LGPL-3.
"""Projection of native document extraction into the existing flat contract."""

from decimal import Decimal, InvalidOperation
from datetime import datetime
from copy import deepcopy

from jsonschema import validate

from ..schemas.document_extraction import DOCUMENT_EXTRACTION_RESULT_SCHEMA


def normalize_amount(value):
    """Normalize common European and plain decimal representations."""
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return format(Decimal(text), "f")
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid monetary value: %s" % value)


def normalize_date(value):
    if value is None:
        return None
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Invalid invoice date: %s" % value)


def _clues(line):
    clues = line.get("reconciliation_clues") or []
    if not isinstance(clues, list):
        raise ValueError("reconciliation_clues must be a list.")
    result = [{"label": str(item["label"]), "value": item["value"]} for item in clues]
    known_clue_keys = {
        "ref": "Ref",
        "reference": "Reference",
        "our_reference": "Our reference",
        "your_reference": "Your reference",
        "load_ref": "Load ref",
        "shipping_ref": "Shipping ref",
        "shipment_ref": "Shipment ref",
        "booking_ref": "Booking ref",
        "pickup_ref": "Pickup ref",
        "carrier_ref": "Carrier ref",
        "customer_ref": "Customer ref",
    }
    for key, label in known_clue_keys.items():
        if key in line and line[key] not in (None, ""):
            result.append({"label": label, "value": line[key]})
    return result


def _description(line, clues):
    labels = (
        ("Loading Date", "loading_date"),
        ("Unloading Date", "unloading_date"),
        ("Our Reference", "our_reference"),
        ("Your Reference", "your_reference"),
        ("Shipment Reference", "shipment_reference"),
        ("Load Reference", "load_ref"),
        ("Booking Reference", "booking_ref"),
        ("Loading Address", "loading_address"),
        ("Unloading Address", "unloading_address"),
        ("Cargo", "description"),
        ("Weight", "gross_weight"),
        ("Volume Weight", "volume_weight"),
        ("Volume", "volume"),
    )
    description = [
        "%s: %s" % (label, line[key])
        for label, key in labels
        if line.get(key) not in (None, "")
    ]
    known_values = {line.get(key) for _, key in labels}
    description.extend(
        "%s: %s" % (item["label"], item["value"])
        for item in clues
        if item["value"] not in known_values
    )
    return "\n".join(description) or None


def _charge_details(line):
    charges = line.get("charge_components")
    if charges is not None:
        if not isinstance(charges, list):
            raise ValueError("charge_components must be a list.")
        return "\n".join(
            "%s: %s" % (item["description"], item["amount"])
            for item in charges
            if item.get("description") not in (None, "")
            and item.get("amount") not in (None, "")
        ) or None
    charges = line.get("charges") or {}
    if not isinstance(charges, dict):
        raise ValueError("charges must be an object.")
    return "\n".join(
        "%s: %s" % (label, value)
        for label, value in charges.items()
        if value not in (None, "")
    ) or None


def _normalize_native_document(document):
    """Accept the flat Luna invoice shape as well as the native contract."""
    if "invoice" in document:
        return document
    if "lines" in document and "supplier" in document:
        supplier = document.get("supplier") or {}
        lines = []
        for source_line in document["lines"]:
            line = dict(source_line)
            line["description"] = line.get("unit_description")
            lines.append(line)
        return {
            "document_type": "FACTUUR",
            "invoice": {
                "issuer": {"name": supplier.get("name")},
                "invoice_number": document.get("invoice_number"),
                "invoice_date": document.get("invoice_date"),
                "currency": document.get("currency"),
                "lines": lines,
                "subtotal": document.get("subtotal"),
                "total_tax": document.get("total_tax"),
                "total_amount": document.get("total_amount"),
            },
        }
    if not isinstance(document.get("line_items"), list):
        return document
    seller = document.get("seller") or {}
    totals = document.get("totals") or {}
    invoice = {
        "issuer": {"name": seller.get("name")} if seller else {},
        "invoice_number": document.get("invoice_number"),
        "invoice_date": document.get("invoice_date"),
        "currency": document.get("currency"),
        "lines": [],
        "totals": {
            "total_excluding_vat": totals.get("total_excluding_vat"),
            "vat_amount": totals.get("vat_amount"),
            "total_including_vat": totals.get("total_including_vat"),
        },
    }
    for source_line in document["line_items"]:
        line = dict(source_line)
        line["description"] = line.get("unit_description") or line.get("description")
        if "total_amount" in line or "amount" in line:
            line["amount"] = line.get("total_amount") or line.get("amount")
        invoice["lines"].append(line)
    return {
        "document_type": document.get("document_type") or "FACTUUR",
        "invoice": invoice,
    }


def _normalize_native_document_aliases(document):
    """Copy only the known provider aliases into the extraction contract."""
    normalized = deepcopy(document)
    invoice = normalized.get("invoice")
    if not isinstance(invoice, dict) or not isinstance(invoice.get("lines"), list):
        return normalized
    if "subtotal" not in invoice and "subtotal_excluding_tax" in invoice:
        invoice["subtotal"] = invoice["subtotal_excluding_tax"]
    if "total_amount" not in invoice and "total_including_tax" in invoice:
        invoice["total_amount"] = invoice["total_including_tax"]
    tax = invoice.get("tax")
    if (
        "total_tax" not in invoice
        and isinstance(tax, dict)
        and "amount" in tax
    ):
        invoice["total_tax"] = tax["amount"]
    for line in invoice["lines"]:
        if not isinstance(line, dict):
            continue
        if "amount" not in line and "amount_excl_tax" in line:
            line["amount"] = line["amount_excl_tax"]
        if "amount" not in line and "line_total" in line:
            line["amount"] = line["line_total"]
        charges = line.get("charge_components")
        if isinstance(charges, list):
            for charge in charges:
                if (
                    isinstance(charge, dict)
                    and "description" not in charge
                    and "label" in charge
                ):
                    charge["description"] = charge["label"]
            continue
        charges = line.get("charges")
        if isinstance(charges, list):
            line["charge_components"] = [
                {
                    **charge,
                    "description": (
                        charge.get("description")
                        if charge.get("description") not in (None, "")
                        else charge.get("label")
                    ),
                }
                if isinstance(charge, dict) else charge
                for charge in charges
            ]
    return normalized


def _supplier_raw_text(invoice, issuer):
    supplier = invoice.get("supplier")
    if supplier in (None, ""):
        supplier = invoice.get("supplier_name") or issuer.get("name")
    if isinstance(supplier, dict):
        name = supplier.get("name")
        return name if isinstance(name, str) and name.strip() else supplier
    return supplier


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def document_to_canonical(document):
    """Create one Canonical line for each document business line."""
    document = _normalize_native_document_aliases(
        _normalize_native_document(document)
    )
    validate(document, DOCUMENT_EXTRACTION_RESULT_SCHEMA)
    invoice = document["invoice"]
    totals = invoice.get("totals") or {}
    issuer = invoice.get("issuer") or {}
    lines = []
    for source_line in invoice["lines"]:
        clues = _clues(source_line)
        lines.append({
            "description": {
                "value": _description(source_line, clues),
                "confidence": 0.0,
            },
            "amount": {
                "value": normalize_amount(source_line.get("amount")),
                "confidence": 0.0,
            },
            "tax_raw_text": {
                "value": source_line.get("tax_raw_text"),
                "confidence": 0.0,
            },
            "tax_rate": {
                "value": source_line.get("tax_rate"),
                "confidence": 0.0,
            },
            "tax_amount": {
                "value": normalize_amount(source_line.get("tax_amount")),
                "confidence": 0.0,
            },
            "reconciliation_clue": None,
            "charge_details": _charge_details(source_line),
            "reconciliation_clues": clues,
        })
    return {
        "header": {
            "invoice_number": {"value": invoice.get("invoice_number"), "confidence": 0.0},
            "invoice_date": {
                "value": normalize_date(invoice.get("invoice_date")),
                "confidence": 0.0,
            },
            "supplier_raw_text": {
                "value": _supplier_raw_text(invoice, issuer),
                "confidence": 0.0,
            },
            "currency_raw_text": {"value": invoice.get("currency"), "confidence": 0.0},
            "total_amount": {
                "value": normalize_amount(
                    _first_present(
                        invoice.get("grand_total"),
                        invoice.get("total_amount"),
                        totals.get("total_including_vat"),
                        totals.get("total_incl_tax"),
                        totals.get("total_incl_vat"),
                    )
                ),
                "confidence": 0.0,
            },
            "total_tax": {
                "value": normalize_amount(
                    _first_present(
                        invoice.get("tax_total"),
                        invoice.get("total_tax"),
                        totals.get("vat_amount"),
                        totals.get("tax_total"),
                    )
                ),
                "confidence": 0.0,
            },
            "subtotal": {
                "value": normalize_amount(
                    _first_present(
                        invoice.get("subtotal"),
                        totals.get("subtotal_excl_tax"),
                        totals.get("subtotal_excl_vat"),
                    )
                ),
                "confidence": 0.0,
            },
        },
        "lines": lines,
        "is_multi_invoice": False,
    }
