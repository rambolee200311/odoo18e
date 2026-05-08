# -*- coding: utf-8 -*-

from odoo import models
from odoo.exceptions import AccessError

from .utils import portal_owner_partner


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def validate_access(self, access_token):
        try:
            return super().validate_access(access_token)
        except AccessError:
            if access_token or not self.env.user._is_portal():
                raise
            self.ensure_one()
            if self.marstek_can_portal_read():
                return self.sudo()
            raise

    def marstek_can_portal_read(self):
        owner = portal_owner_partner(self.env)
        if not owner:
            return False
        attachment = self.sudo()
        model_owner_fields = {
            "world.depot.inbound.order": "project.owner",
            "world.depot.outbound.order": "project.owner",
            "world.depot.inbound.order.docs": "inbound_order_id.project.owner",
            "world.depot.outbound.order.docs": "outbound_order_id.project.owner",
        }
        owner_field = model_owner_fields.get(attachment.res_model)
        if not owner_field or not attachment.res_id:
            return False
        record_env = self.env[attachment.res_model].sudo()
        record = record_env.search([("id", "=", attachment.res_id), (owner_field, "=", owner.id)], limit=1)
        return bool(record)
