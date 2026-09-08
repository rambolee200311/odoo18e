# © 2024 Wukong Digital. License LGPL-3.
"""Generic reconciliation-clue schema shared by extraction and review values."""

RECONCILIATION_CLUE_SCHEMA = {
    "type": "object",
    "required": ["label", "value"],
    "additionalProperties": False,
    "properties": {
        "label": {"type": "string", "minLength": 1},
        "value": {"type": ["string", "number"]},
    },
}
