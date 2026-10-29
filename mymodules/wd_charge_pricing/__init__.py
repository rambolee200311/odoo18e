# -*- coding: utf-8 -*-

from . import models
from . import wizard


def migrate_charge_pricing_xml_ids(env):
    env_xml_data = env["ir.model.data"]
    xml_data = env_xml_data.sudo().search([("module", "=", "wd_iffm"), ("name", "=", "seq_charge_quotation")])
    if xml_data:
        env_xml_data.browse(xml_data.ids).write({"module": "wd_charge_pricing"})
