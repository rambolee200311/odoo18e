# -*- coding: utf-8 -*-

from . import models
from . import wizard


def migrate_charge_pricing_xml_ids(env):
    env_xml_data = env["ir.model.data"]
    xml_data_ids = env_xml_data.sudo().search([
        ("module", "=", "wd_iffm"),
        ("name", "in", [
            "seq_charge_quotation",
            "seq_statement_period",
            "model_statement_period",
            "access_statement_period_user",
            "view_statement_period_tree",
            "view_statement_period_form",
            "action_statement_period",
            "menu_statement_period",
            "menu_wd_charge_quotation",
            "menu_wd_charge_receivable_quotation",
            "menu_wd_charge_payable_quotation",
            "charge_account_menu",
            "charge_item_menu",
            "menu_wd_charge_unit",
        ]),
    ]).ids
    if xml_data_ids:
        env_xml_data.browse(xml_data_ids).write({"module": "wd_charge_pricing"})
