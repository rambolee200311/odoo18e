# © 2024 Wukong Digital. License LGPL-3.
from unittest import TestCase

from jsonschema import ValidationError

from ..services.native_document_projection import (
    _normalize_native_document_aliases,
    document_to_canonical,
)


def _line(**values):
    return {"description": "Freight", **values}


class TestNativeDocumentAliases(TestCase):
    def test_strict_invoice_extraction_result_projects_as_one_line(self):
        canonical = document_to_canonical({
            "invoice_number": "INV-1",
            "invoice_date": "2026-08-10",
            "due_date": None,
            "currency": "EUR",
            "supplier": {"name": "Bring Cargo B.V.", "address": None, "vat_number": None},
            "buyer": {"name": None, "address": None},
            "lines": [{
                "reference": "REF-1",
                "our_reference": None,
                "loading_date": None,
                "unloading_date": None,
                "loading_address": None,
                "unloading_address": None,
                "quantity": None,
                "unit_description": "Freight",
                "gross_weight": None,
                "volume_weight": None,
                "volume": None,
                "charge_components": [{"description": "Fuel", "amount": 10.5}],
                "amount": 100.0,
            }],
            "subtotal": 100.0,
            "total_tax": 21.0,
            "total_amount": 121.0,
        })
        self.assertEqual(len(canonical["lines"]), 1)
        self.assertEqual(canonical["header"]["supplier_raw_text"]["value"], "Bring Cargo B.V.")
        self.assertEqual(canonical["header"]["total_amount"]["value"], "121.0")

    def test_standard_amount_is_preserved(self):
        normalized = _normalize_native_document_aliases({
            "invoice": {"lines": [_line(amount=15.0, amount_excl_tax=10.0)]},
        })
        self.assertEqual(normalized["invoice"]["lines"][0]["amount"], 15.0)

    def test_amount_excl_tax_is_normalized(self):
        document = {"invoice": {"lines": [_line(amount_excl_tax=15.0)]}}
        normalized = _normalize_native_document_aliases(document)
        self.assertEqual(normalized["invoice"]["lines"][0]["amount"], 15.0)
        document_to_canonical({
            "document_type": "invoice",
            **normalized,
        })

    def test_missing_amount_alias_still_fails_schema_validation(self):
        with self.assertRaises(ValidationError):
            document_to_canonical({
                "document_type": "invoice",
                "invoice": {"lines": [_line()]},
            })

    def test_standard_charge_description_is_preserved(self):
        normalized = _normalize_native_document_aliases({
            "invoice": {
                "lines": [_line(charge_components=[{
                    "description": "Canonical",
                    "label": "Provider",
                    "amount": 100,
                }])],
            },
        })
        charge = normalized["invoice"]["lines"][0]["charge_components"][0]
        self.assertEqual(charge["description"], "Canonical")

    def test_charge_label_is_normalized(self):
        normalized = _normalize_native_document_aliases({
            "invoice": {
                "lines": [_line(charge_components=[{
                    "label": "Transportkosten",
                    "amount": 100,
                }])],
            },
        })
        charge = normalized["invoice"]["lines"][0]["charge_components"][0]
        self.assertEqual(charge["description"], "Transportkosten")

    def test_charges_list_is_normalized_to_charge_components(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "lines": [_line(charges=[{
                    "label": "Dieselolietoeslag",
                    "amount": "107,62",
                    "currency": "EUR",
                }])],
            },
        })
        self.assertEqual(
            canonical["lines"][0]["charge_details"],
            "Dieselolietoeslag: 107,62",
        )

    def test_multiple_charges_remain_on_one_canonical_line(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "lines": [_line(charges=[
                    {"label": "Extra kosten", "amount": "75,00"},
                    {"label": "Dieselolietoeslag", "amount": "107,62"},
                    {"label": "Transportkosten", "amount": "413,92"},
                ])],
            },
        })
        self.assertEqual(len(canonical["lines"]), 1)
        self.assertEqual(canonical["lines"][0]["charge_details"].count("\n"), 2)

    def test_two_business_lines_keep_four_charges_each(self):
        lines = [
            _line(charges=[
                {"label": "Charge %s" % index, "amount": index}
                for index in range(1, 5)
            ])
            for _ in range(2)
        ]
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {"lines": lines},
        })
        self.assertEqual(len(canonical["lines"]), 2)
        self.assertEqual(
            [line["charge_details"].count("\n") for line in canonical["lines"]],
            [3, 3],
        )

    def test_formal_charge_components_win_over_charges_list(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "lines": [_line(
                    charge_components=[{
                        "description": "Formal",
                        "amount": "10.00",
                    }],
                    charges=[{"label": "Provider", "amount": "99.00"}],
                )],
            },
        })
        self.assertEqual(canonical["lines"][0]["charge_details"], "Formal: 10.00")

    def test_charges_object_remains_supported(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "lines": [_line(charges={
                    "Dieselolietoeslag": "107.62",
                    "Extra kosten": "75.00",
                })],
            },
        })
        self.assertEqual(
            canonical["lines"][0]["charge_details"],
            "Dieselolietoeslag: 107.62\nExtra kosten: 75.00",
        )

    def test_malformed_charge_list_is_rejected(self):
        with self.assertRaises(ValidationError):
            document_to_canonical({
                "document_type": "invoice",
                "invoice": {
                    "lines": [_line(charges=[{"label": "Missing amount"}])],
                },
            })

    def test_unknown_amount_field_is_not_fuzzy_mapped(self):
        with self.assertRaises(ValidationError):
            document_to_canonical({
                "document_type": "invoice",
                "invoice": {"lines": [_line(net_amount=15.0)]},
            })

    def test_string_supplier_is_projected_as_string(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "supplier": "Bring Cargo B.V.",
                "lines": [_line(amount=15.0)],
            },
        })
        self.assertEqual(
            canonical["header"]["supplier_raw_text"]["value"],
            "Bring Cargo B.V.",
        )

    def test_structured_supplier_projects_its_name(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "supplier": {
                    "name": "Bring Cargo B.V.",
                    "address": "Griendwerkersstraat 10",
                    "vat_number": "NL008225497B01",
                },
                "lines": [_line(amount=15.0)],
            },
        })
        supplier = canonical["header"]["supplier_raw_text"]["value"]
        self.assertIsInstance(supplier, str)
        self.assertEqual(supplier, "Bring Cargo B.V.")

    def test_supplier_without_name_is_not_stringified(self):
        with self.assertRaises(ValidationError):
            document_to_canonical({
                "document_type": "invoice",
                "invoice": {
                    "supplier": {"address": "Griendwerkersstraat 10"},
                    "lines": [_line(amount=15.0)],
                },
            })

    def test_proven_native_total_aliases_are_projected(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "totals": {
                    "subtotal_excl_tax": "15,00",
                    "tax_total": "3,15",
                    "total_incl_tax": "18,15",
                },
                "lines": [_line(amount=15.0)],
            },
        })
        header = canonical["header"]
        self.assertEqual(header["subtotal"]["value"], "15.00")
        self.assertEqual(header["total_tax"]["value"], "3.15")
        self.assertEqual(header["total_amount"]["value"], "18.15")

    def test_standard_total_fields_win_over_aliases(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "subtotal": "20.00",
                "total_tax": "4.00",
                "total_amount": "24.00",
                "totals": {
                    "subtotal_excl_tax": "15.00",
                    "tax_total": "3.00",
                    "total_incl_tax": "18.00",
                },
                "lines": [_line(amount=20.0)],
            },
        })
        header = canonical["header"]
        self.assertEqual(header["subtotal"]["value"], "20.00")
        self.assertEqual(header["total_tax"]["value"], "4.00")
        self.assertEqual(header["total_amount"]["value"], "24.00")

    def test_missing_totals_are_not_recalculated(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "lines": [_line(amount=15.0)],
            },
        })
        header = canonical["header"]
        self.assertIsNone(header["subtotal"]["value"])
        self.assertIsNone(header["total_tax"]["value"])
        self.assertIsNone(header["total_amount"]["value"])

    def test_vat_total_aliases_are_projected(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "totals": {
                    "subtotal_excl_vat": "960,05",
                    "vat_amount": "201,61",
                    "total_incl_vat": "1.161,66",
                },
                "lines": [_line(amount="601,29"), _line(amount="358,76")],
            },
        })
        header = canonical["header"]
        self.assertEqual(header["subtotal"]["value"], "960.05")
        self.assertEqual(header["total_tax"]["value"], "201.61")
        self.assertEqual(header["total_amount"]["value"], "1161.66")

    def test_standard_and_tax_alias_precedence_is_preserved(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "subtotal": "10.00",
                "total_tax": "2.00",
                "total_amount": "12.00",
                "totals": {
                    "subtotal_excl_tax": "11.00",
                    "subtotal_excl_vat": "12.00",
                    "tax_total": "3.00",
                    "vat_amount": "4.00",
                    "total_incl_tax": "14.00",
                    "total_incl_vat": "15.00",
                },
                "lines": [_line(amount="10.00")],
            },
        })
        header = canonical["header"]
        self.assertEqual(header["subtotal"]["value"], "10.00")
        self.assertEqual(header["total_tax"]["value"], "2.00")
        self.assertEqual(header["total_amount"]["value"], "12.00")

    def test_provider_call_196_aliases_are_projected(self):
        canonical = document_to_canonical({
            "document_type": "invoice",
            "invoice": {
                "supplier": {"name": "Bring Cargo B.V."},
                "subtotal_excluding_tax": 924.73,
                "total_including_tax": 1118.92,
                "tax": {"rate": 21, "amount": 194.19},
                "lines": [_line(
                    line_total=924.73,
                    charges=[{
                        "description": "Fuel surcharge",
                        "amount": 10.00,
                    }],
                )],
            },
        })
        header = canonical["header"]
        self.assertEqual(header["subtotal"]["value"], "924.73")
        self.assertEqual(header["total_tax"]["value"], "194.19")
        self.assertEqual(header["total_amount"]["value"], "1118.92")
        self.assertEqual(canonical["lines"][0]["amount"]["value"], "924.73")
