# © 2024 Wukong Digital. License LGPL-3.
"""Schema for the transport-invoice facts extracted from one PDF page."""

PAGE_EXTRACTION_RESULT_SCHEMA = {
    "type": "object",
    "required": ["page_number"],
    "additionalProperties": False,
    "properties": {
        "page_number": {"type": "integer", "minimum": 1},
        "header": {
            "type": "object",
            "additionalProperties": {
                "type": ["string", "number", "null"],
            },
        },
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": {
                    "type": ["string", "number", "null"],
                },
                "properties": {
                    "raw_fields": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/raw_fact"},
                    },
                },
            },
        },
        "raw_facts": {
            "type": "array",
            "items": {"$ref": "#/$defs/raw_fact"},
        },
    },
    "$defs": {
        "raw_fact": {
            "type": "object",
            "required": ["source_label", "source_value"],
            "additionalProperties": False,
            "properties": {
                "source_label": {"type": "string"},
                "source_value": {"type": ["string", "number", "null"]},
            },
        },
    },
}
