# © 2024 Wukong Digital. License LGPL-3.
"""MappingResult JSON Schema (structural definition only)."""

MAPPING_RESULT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "supplier_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "partner_id": {"type": ["integer", "null"]},
                    "name": {"type": "string"},
                    "match_score": {"type": "number"},
                    "match_type": {"type": "string"},
                    "matched_rule_id": {"type": ["integer", "null"]},
                },
            },
        },
        "product_candidates": {"type": "array"},
        "tax_candidates": {"type": "array"},
        "currency_candidates": {"type": "array"},
    },
}
