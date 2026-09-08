# © 2024 Wukong Digital. License LGPL-3.
"""Minimal document-level extraction contract for native document providers."""

from .reconciliation_clue import RECONCILIATION_CLUE_SCHEMA

DOCUMENT_EXTRACTION_RESULT_SCHEMA = {
    "type": "object",
    "required": ["document_type", "invoice"],
    "additionalProperties": True,
    "properties": {
        "document_type": {"type": ["string", "null"]},
        "invoice": {
            "type": "object",
            "required": ["lines"],
            "additionalProperties": True,
            "properties": {
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["description", "amount"],
                        "additionalProperties": True,
                        "properties": {
                            "description": {"type": ["string", "null"]},
                            "amount": {"type": ["string", "number", "null"]},
                            "reconciliation_clues": {
                                "type": "array",
                                "items": RECONCILIATION_CLUE_SCHEMA,
                            },
                            "charge_components": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["description", "amount"],
                                    "additionalProperties": True,
                                    "properties": {
                                        "description": {"type": ["string", "null"]},
                                        "amount": {"type": ["string", "number", "null"]},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}

# This is the fixed contract sent to OpenAI Responses Structured Outputs.
INVOICE_EXTRACTION_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "invoice_number", "invoice_date", "due_date", "currency",
        "supplier", "buyer", "lines", "subtotal", "total_tax", "total_amount",
    ],
    "properties": {
        "invoice_number": {"type": ["string", "null"]},
        "invoice_date": {"type": ["string", "null"]},
        "due_date": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
        "supplier": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "address", "vat_number"],
            "properties": {
                "name": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
                "vat_number": {"type": ["string", "null"]},
            },
        },
        "buyer": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "address"],
            "properties": {
                "name": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
            },
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "reference", "our_reference", "loading_date",
                    "unloading_date", "loading_address", "unloading_address",
                    "quantity", "unit_description", "gross_weight",
                    "volume_weight", "volume", "charge_components", "amount",
                ],
                "properties": {
                    "reference": {"type": ["string", "null"]},
                    "our_reference": {"type": ["string", "null"]},
                    "loading_date": {"type": ["string", "null"]},
                    "unloading_date": {"type": ["string", "null"]},
                    "loading_address": {"type": ["string", "null"]},
                    "unloading_address": {"type": ["string", "null"]},
                    "quantity": {"type": ["number", "null"]},
                    "unit_description": {"type": ["string", "null"]},
                    "gross_weight": {"type": ["number", "null"]},
                    "volume_weight": {"type": ["number", "null"]},
                    "volume": {"type": ["number", "null"]},
                    "charge_components": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["description", "amount"],
                            "properties": {
                                "description": {"type": "string"},
                                "amount": {"type": "number"},
                            },
                        },
                    },
                    "amount": {"type": ["number", "null"]},
                },
            },
        },
        "subtotal": {"type": ["number", "null"]},
        "total_tax": {"type": ["number", "null"]},
        "total_amount": {"type": ["number", "null"]},
    },
}
