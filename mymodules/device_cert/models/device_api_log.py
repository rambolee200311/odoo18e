from odoo import models, fields
# API 访问日志
class DeviceAPILog(models.Model):
    _name = 'device.api.log'
    _description = 'API Verification Logs'
    _order = 'create_date DESC'

    device_id = fields.Char(string='Device Fingerprint')
    cert_serial = fields.Char(string='Cert Serial')
    ip_address = fields.Char(string='IP')
    status = fields.Selection([('allowed', 'Allowed'), ('blocked', 'Blocked'), ('failed', 'Failed')])
    message = fields.Char(string='Message')
    create_date = fields.Datetime(default=fields.Datetime.now)