# © 2024 Wukong Digital. License LGPL-3.
"""review_warnings array element JSON Schema."""

WARNING_ITEM_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["code", "message"],
    "additionalProperties": False,
    "properties": {
        "code": {"type": "string"},
        "message": {"type": "string"},
    },
}

REVIEW_WARNINGS_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "array",
    "items": WARNING_ITEM_SCHEMA,
}
