# -*- coding: utf-8 -*-


def migrate(cr, version):
    xml_id_names = (
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
    )
    cr.execute("UPDATE ir_model_data SET module = %s WHERE module = %s AND name IN %s", ("wd_charge_pricing", "wd_iffm", xml_id_names))
