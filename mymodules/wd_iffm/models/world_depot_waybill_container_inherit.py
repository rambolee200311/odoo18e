from odoo import api, fields, models, _
class WaybillContainerInherit(models.Model):
    _inherit = "world.depot.waybill.container"
    _rec_name = 'container_number'