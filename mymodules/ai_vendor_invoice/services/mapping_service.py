# © 2024 Wukong Digital. License LGPL-3.
"""Candidate mapping; this service never writes mapping master data."""

from difflib import SequenceMatcher


def _candidates(records, text, value_key, label_key, rule_key):
    text = (text or "").strip().lower()
    if not text:
        return []
    result = []
    for record in records:
        label = (getattr(record, label_key) or "").strip()
        score = SequenceMatcher(None, text, label.lower()).ratio()
        if score:
            result.append({
                value_key: getattr(record, rule_key).id,
                "name": label,
                "match_score": score,
                "match_type": "exact" if score == 1 else "fuzzy",
                "matched_rule_id": record.id,
            })
    return sorted(result, key=lambda item: item["match_score"], reverse=True)


def do_mapping(env, canonical_result):
    header = canonical_result.get("header", {})
    supplier = header.get("supplier_raw_text", {}).get("value")
    currency = header.get("currency_raw_text", {}).get("value")
    supplier_records = env["wd.mapping.vendor_alias"].search([("active", "=", True)])
    currency_records = env["wd.mapping.currency_text"].search([("active", "=", True)])
    products = env["wd.mapping.product_keyword"].search([("active", "=", True)])
    taxes = env["wd.mapping.tax_text"].search([("active", "=", True)])
    result = {
        "supplier_candidates": _candidates(
            supplier_records, supplier, "partner_id", "alias_text", "partner_id"
        ),
        "currency_candidates": _candidates(
            currency_records, currency, "currency_id", "currency_raw_text", "currency_id"
        ),
        "product_candidates": [],
        "tax_candidates": [],
    }
    for line in canonical_result.get("lines", []):
        description = line.get("description", {}).get("value")
        tax_text = line.get("tax_raw_text", {}).get("value")
        result["product_candidates"].append(_candidates(
            products, description, "product_id", "keyword", "product_id"
        ))
        result["tax_candidates"].append(_candidates(
            taxes, tax_text, "tax_id", "tax_raw_text", "tax_id"
        ))
    return result
