# -*- coding: utf-8 -*-

from . import models


def migrate_account_extension_xml_ids(env):
    xml_data_model = env["ir.model.data"]
    xml_data = xml_data_model.sudo().search([("module", "=", "wd_iffm"), ("name", "in", ["acc_pay_expense", "acc_clearance_expense_account", "acc_hanover_expense_account", "account_account_view_form_inherit_logistics_category", "account_account_view_list_inherit_logistics_category", "account_move_form_inherit_charge_item"])])
    if xml_data:
        xml_data_model.browse(xml_data.ids).write({"module": "wd_account_extension"})
