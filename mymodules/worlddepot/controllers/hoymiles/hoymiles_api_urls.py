from odoo import models, api, fields
import requests
import json
from datetime import datetime, timedelta
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class APIUrls(models.Model):
    _name = 'hoymiles.api.urls'
    _description = 'Hoymiles API URLs'

    name = fields.Char(string='API Name', required=True)
    url = fields.Char(string='API URL', required=True)
    parameters_form = fields.Text(string='Parameters (Key=Value format)')
    parameters_json = fields.Text(string='Parameters (JSON format)')
    response_example = fields.Text(string='Response Example')
    description = fields.Text(string='Description')




