# © 2024 Wukong Digital. License LGPL-3.
"""
HumanReviewResult JSON Schema.
T-006 / T-007: Bill Creator reads ONLY this object.
"""

from .reconciliation_clue import RECONCILIATION_CLUE_SCHEMA

HUMAN_REVIEW_RESULT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "header": {
            "type": "object",
            "properties": {
                "supplier_id": {"type": ["integer", "null"]},
                "invoice_number": {"type": ["string", "null"]},
                "invoice_date": {
                    "type": ["string", "null"],
                    "format": "date",
                },
                "currency_id": {"type": ["integer", "null"]},
                "total_amount": {"type": ["string", "null"]},
                "total_tax": {"type": ["string", "null"]},
                "subtotal": {"type": ["string", "null"]},
            },
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_id": {"type": ["integer", "null"]},
                    "description": {"type": ["string", "null"]},
                    "quantity": {"type": ["string", "null"]},
                    "unit_price": {"type": ["string", "null"]},
                    "subtotal": {"type": ["string", "null"]},
                    "tax_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "tax_amount": {"type": ["string", "null"]},
                    "line_total_amount": {"type": ["string", "null"]},
                    "reconciliation_clues": {
                        "type": "array",
                        "items": RECONCILIATION_CLUE_SCHEMA,
                    },
                },
            },
        },
    },
}
