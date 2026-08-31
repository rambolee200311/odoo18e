# -*- coding: utf-8 -*-

from odoo import models
from odoo.exceptions import AccessError

from .utils import portal_project_domain


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def validate_access(self, access_token):
        try:
            return super().validate_access(access_token)
        except AccessError:
            if access_token or not self.env.user._is_portal():
                raise
            self.ensure_one()
            if self.stock_operation_can_portal_read():
                return self.sudo()
            raise

    def stock_operation_can_portal_read(self):
        attachment = self.sudo()
        model_project_fields = {
            "world.depot.inbound.order": "project",
            "world.depot.outbound.order": "project",
            "world.depot.inbound.order.docs": "inbound_order_id.project",
            "world.depot.outbound.order.docs": "outbound_order_id.project",
        }
        project_field = model_project_fields.get(attachment.res_model)
        if not project_field or not attachment.res_id:
            return False
        record_env = self.env[attachment.res_model].sudo()
        record = record_env.search([("id", "=", attachment.res_id)] + portal_project_domain(self.env, project_field), limit=1)
        return bool(record)
