# -*- coding: utf-8 -*-

import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OperationWorkbenchLane(models.Model):
    _name = "operation.workbench.lane"
    _description = "Operation Workbench Lane"
    _order = "sequence asc, id asc"

    name = fields.Char(string="Lane Name", required=True, index=True)
    code = fields.Char(
        string="Lane Code",
        required=True,
        index=True,
        help="Stable key for logic (waybill / handover / clearance) or a unique key for custom lanes.",
    )
    sequence = fields.Integer(string="Sequence", default=10, index=True, help="Display order of the lane")
    active = fields.Boolean(string="Active", default=True, index=True)

    _sql_constraints = [
        ("uniq_code", "unique(code)", "Lane code must be unique."),
    ]

    SYSTEM_CODES = frozenset({"waybill", "handover", "clearance"})

    @api.model
    def _generate_unique_code(self, base_name):
        slug = re.sub(r"[^a-z0-9]+", "_", (base_name or "lane").lower()).strip("_") or "lane"
        if len(slug) > 40:
            slug = slug[:40]
        code = slug
        suffix = 0
        while self.search_count([("code", "=", code)]):
            suffix += 1
            code = f"{slug}_{suffix}"
        return code

    @api.model
    def name_create(self, name):
        """Used by Kanban column quick-create (+ stage)."""
        name = (name or "").strip() or _("New stage")
        code = self._generate_unique_code(name)
        max_seq = self.search([], order="sequence desc", limit=1).sequence or 0
        record = self.create({"name": name, "code": code, "sequence": max_seq + 10})
        return record.id, record.name

    # def unlink(self):
    #     protected = self.filtered(lambda r: r.code in self.SYSTEM_CODES)
    #     if protected:
    #         raise UserError(_("Cannot delete system lanes: %s") % ", ".join(protected.mapped("name")))
    #     return super().unlink()
