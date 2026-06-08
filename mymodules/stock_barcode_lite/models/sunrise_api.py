# -*- coding: utf-8 -*-

from odoo import fields, models


class SunriseApiConfig(models.Model):
    _name = "sunrise.api.config"
    _description = "Sunrise U8C API Config"
    _order = "id desc"

    name = fields.Char(string="Name", required=True, index=True)
    active = fields.Boolean(string="Active", default=True)
    api_type = fields.Selection([("inbound", "Inbound"), ("outbound", "Outbound")], string="API Type", required=True, index=True)
    url = fields.Char(string="API URL", required=True)
    data_url = fields.Char(string="Data URL", required=True)
    path_info = fields.Char(string="Path Info", required=True, default="ic.purchasein.save.sign")
    usercode = fields.Char(string="User Code", required=True)
    password = fields.Char(string="Password", required=True)
    trantype = fields.Char(string="Tran Type", default="code", required=True)
    system = fields.Char(string="System", required=True)
    timeout = fields.Integer(string="Timeout", default=10)
    parameters_json = fields.Text(string="Parameters JSON", copy=False)
    response_example = fields.Text(string="Response Example", copy=False)
    description = fields.Text(string="Description", copy=False)


class SunriseApiLog(models.Model):
    _name = "sunrise.api.log"
    _description = "Sunrise U8C API Log"
    _order = "id desc"

    request_source = fields.Char(string="Request Source", copy=False, index=True)
    request_time = fields.Datetime(string="Request Time", copy=False, index=True)
    request_path = fields.Char(string="Request Path", copy=False)
    request_data = fields.Text(string="Request Data", copy=False)
    response_data = fields.Text(string="Response Data", copy=False)
    exception_details = fields.Text(string="Exception Details", copy=False)
