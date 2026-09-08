# © 2024 Wukong Digital. License LGPL-3.
"""
CanonicalInvoiceResult JSON Schema.
Each extractable field is represented as {"value": ..., "confidence": 0..1}.
T-010: structure validation only; business logic lives in validation_service.
"""

from .reconciliation_clue import RECONCILIATION_CLUE_SCHEMA

CANONICAL_INVOICE_RESULT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["header", "lines", "is_multi_invoice"],
    "additionalProperties": False,
    "properties": {
        "header": {
            "type": "object",
            "required": [
                "invoice_number",
                "invoice_date",
                "supplier_raw_text",
                "currency_raw_text",
                "total_amount",
                "total_tax",
            ],
            "additionalProperties": False,
            "properties": {
                "invoice_number": {
                    "type": "object",
                    "required": ["value", "confidence"],
                    "additionalProperties": False,
                    "properties": {
                        "value": {"type": ["string", "null"]},
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                },
                "invoice_date": {
                    "type": "object",
                    "required": ["value", "confidence"],
                    "additionalProperties": False,
                    "properties": {
                        "value": {
                            "type": ["string", "null"],
                            "format": "date",
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                },
                "supplier_raw_text": {
                    "type": "object",
                    "required": ["value", "confidence"],
                    "additionalProperties": False,
                    "properties": {
                        "value": {"type": ["string", "null"]},
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                },
                "currency_raw_text": {
                    "type": "object",
                    "required": ["value", "confidence"],
                    "additionalProperties": False,
                    "properties": {
                        "value": {"type": ["string", "null"]},
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                },
                "total_amount": {
                    "type": "object",
                    "required": ["value", "confidence"],
                    "additionalProperties": False,
                    "properties": {
                        "value": {"type": ["string", "null"]},
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                },
                "total_tax": {
                    "type": "object",
                    "required": ["value", "confidence"],
                    "additionalProperties": False,
                    "properties": {
                        "value": {"type": ["string", "null"]},
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                    },
                },
                "subtotal": {
                        "type": "object",
                        "required": ["value", "confidence"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["string", "null"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["description", "amount", "tax_raw_text"],
                "additionalProperties": False,
                "properties": {
                    "description": {
                        "type": "object",
                        "required": ["value", "confidence"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["string", "null"]},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                    },
                    "amount": {
                        "type": "object",
                        "required": ["value", "confidence"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["string", "null"]},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                    },
                    "tax_raw_text": {
                        "type": "object",
                        "required": ["value", "confidence"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["string", "null"]},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                    },
                    "tax_rate": {
                        "type": "object",
                        "required": ["value", "confidence"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["number", "string", "null"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    },
                    "tax_amount": {
                        "type": "object",
                        "required": ["value", "confidence"],
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": ["string", "null"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                    },
                    "reconciliation_clue": {"type": ["string", "null"]},
                    "charge_details": {"type": ["string", "null"]},
                    "reconciliation_clues": {
                        "type": "array",
                        "items": RECONCILIATION_CLUE_SCHEMA,
                    },
                },
            },
        },
        "is_multi_invoice": {"type": "boolean"},
    },
}
