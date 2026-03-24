from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class OperationWorkbenchCard(models.Model):
    _name = "operation.workbench.card"
    _description = "Operation Workbench Card"
    _order = "id desc"

    name = fields.Char(string="Card Name", required=True, index=True, copy=False)
    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True, index=True, ondelete="cascade")
    lane_code = fields.Selection([("waybill", "Waybill"), ("handover", "Handover"), ("clearance", "Clearance"), ("lane4", "Lane 4")], string="Lane", required=True, index=True)
    source_model = fields.Char(string="Source Model", required=True, index=True)
    source_id = fields.Integer(string="Source ID", required=True, index=True)
    is_main = fields.Boolean(string="Is Main", default=False, index=True)
    parent_card_id = fields.Many2one("operation.workbench.card", string="Parent Card", index=True, ondelete="set null")
    child_lines = fields.One2many("operation.workbench.card", "parent_card_id", string="Child Cards")
    display_state = fields.Char(string="Display State", index=True)
    sequence = fields.Integer(string="Sequence", default=10, index=True)
    extra_data = fields.Json(string="Extra Data")
    active = fields.Boolean(string="Active", default=True, index=True)

    _sql_constraints = [
        ("uniq_workbench_source", "unique(source_model,source_id)", "Source model and source id must be unique."),
    ]

    @api.constrains("waybill_id", "lane_code", "is_main", "active")
    def check_unique_main_card(self):
        env_card = self.env["operation.workbench.card"]
        single_main_lanes = {"waybill", "handover"}  # clearance 不在这里

        for rec in self:
            if not rec.active or not rec.is_main:
                continue
            if rec.lane_code not in single_main_lanes:
                continue

            count = env_card.sudo().search_count([
                ("id", "!=", rec.id),
                ("waybill_id", "=", rec.waybill_id.id),
                ("lane_code", "=", rec.lane_code),
                ("is_main", "=", True),
                ("active", "=", True),
            ])
            if count:
                raise ValidationError(_("Main card already exists in lane %s.") % rec.lane_code)

    @api.model
    def action_sync_cards_by_waybill(self, waybill_id):
        env_card = self.env["operation.workbench.card"]
        env_waybill = self.env["world.depot.waybill"]
        env_handover = self.env["operation.order.handover"]
        env_clearance = self.env["operation.order.clearance"]

        waybill = env_waybill.sudo().browse(waybill_id).exists()
        if not waybill:
            raise ValidationError(_("Waybill not found."))

        waybill_card = env_card.sudo().search([("waybill_id", "=", waybill.id), ("lane_code", "=", "waybill"), ("active", "=", True)], limit=1)
        waybill_vals = {
            "name": waybill.billno or waybill.bl_number or waybill.hbl_number or str(waybill.id),
            "waybill_id": waybill.id,
            "lane_code": "waybill",
            "source_model": "world.depot.waybill",
            "source_id": waybill.id,
            "is_main": True,
            "display_state": waybill.state or "",
            "sequence": 1,
            "extra_data": {
                "billno": waybill.billno,
                "bl_number": waybill.bl_number,
                "hbl_number": waybill.hbl_number,
                "container_number": ", ".join([line.container_number for line in waybill.container_ids]),
            },
            "active": True,
        }
        if waybill_card:
            env_card.browse(waybill_card.id).write(waybill_vals)
        else:
            env_card.create(waybill_vals)

        handover_roots = env_handover.sudo().search([("waybill_id", "=", waybill.id), ("parent_id", "=", False), ("state", "!=", "cancelled")], order="id desc")
        handover_children = env_handover.sudo().search([("parent_id", "in", handover_roots.ids), ("state", "!=", "cancelled")], order="id desc") if handover_roots else env_handover.browse()
        self.action_sync_handover_cards(waybill, handover_roots, handover_children)

        clearance_roots = env_clearance.sudo().search([("waybill_id", "=", waybill.id), ("parent_id", "=", False), ("state", "!=", "cancelled")], order="id desc")
        clearance_children = env_clearance.sudo().search([("parent_id", "in", clearance_roots.ids), ("state", "!=", "cancelled")], order="id desc") if clearance_roots else env_clearance.browse()
        self.action_sync_clearance_cards(waybill, clearance_roots, clearance_children)
        return True

    @api.model
    def action_sync_handover_cards(self, waybill, root_lines, child_lines):
        env_card = self.env["operation.workbench.card"]
        existing = env_card.sudo().search([("waybill_id", "=", waybill.id), ("lane_code", "=", "handover"), ("active", "=", True)])
        source_map = {(rec.source_model, rec.source_id): rec.id for rec in existing}
        main_card_map = {}
        seen = set()

        for rec in root_lines:
            key = ("operation.order.handover", rec.id)
            vals = {
                "name": rec.name,
                "waybill_id": waybill.id,
                "lane_code": "handover",
                "source_model": "operation.order.handover",
                "source_id": rec.id,
                "is_main": True,
                "parent_card_id": False,
                "display_state": rec.state or "",
                "sequence": 10,
                "extra_data": {"bill_no": rec.bl_number or rec.hbl_number or rec.obl_number, "container_nums": rec.container_nums, "do_issue_datetime": fields.Datetime.to_string(rec.do_issue_datetime) if rec.do_issue_datetime else False},
                "active": True,
            }
            if key in source_map:
                env_card.browse(source_map[key]).write(vals)
                main_card_map[rec.id] = source_map[key]
            else:
                new_card = env_card.create(vals)
                main_card_map[rec.id] = new_card.id
            seen.add(key)

        for rec in child_lines:
            key = ("operation.order.handover", rec.id)
            vals = {
                "name": rec.name,
                "waybill_id": waybill.id,
                "lane_code": "handover",
                "source_model": "operation.order.handover",
                "source_id": rec.id,
                "is_main": False,
                "parent_card_id": main_card_map.get(rec.parent_id.id),
                "display_state": rec.state or "",
                "sequence": 20,
                "extra_data": {"bill_no": rec.bl_number or rec.hbl_number or rec.obl_number, "container_nums": rec.container_nums, "extra_reason": rec.extra_reason, "extra_remark": rec.extra_remark},
                "active": True,
            }
            if key in source_map:
                env_card.browse(source_map[key]).write(vals)
            else:
                env_card.create(vals)
            seen.add(key)

        stale_ids = [rec.id for rec in existing if (rec.source_model, rec.source_id) not in seen]
        if stale_ids:
            env_card.browse(stale_ids).write({"active": False})

    @api.model
    def action_sync_clearance_cards(self, waybill, root_lines, child_lines):
        env_card = self.env["operation.workbench.card"]
        existing = env_card.sudo().search([("waybill_id", "=", waybill.id), ("lane_code", "=", "clearance"), ("active", "=", True)])
        source_map = {(rec.source_model, rec.source_id): rec.id for rec in existing}
        main_card_map = {}
        seen = set()

        for rec in root_lines:
            key = ("operation.order.clearance", rec.id)
            vals = {
                "name": rec.name,
                "waybill_id": waybill.id,
                "lane_code": "clearance",
                "source_model": "operation.order.clearance",
                "source_id": rec.id,
                "is_main": True,
                "parent_card_id": False,
                "display_state": rec.state or "",
                "sequence": 10,
                "extra_data": {"bill_no": rec.waybill_id.bl_number or rec.waybill_id.hbl_number or rec.waybill_id.obl_number, "container_nums": rec.container_nums, "clearance_finish_datetime": fields.Datetime.to_string(rec.clearance_finish_datetime) if rec.clearance_finish_datetime else False},
                "active": True,
            }
            if key in source_map:
                env_card.browse(source_map[key]).write(vals)
                main_card_map[rec.id] = source_map[key]
            else:
                new_card = env_card.create(vals)
                main_card_map[rec.id] = new_card.id
            seen.add(key)

        for rec in child_lines:
            key = ("operation.order.clearance", rec.id)
            vals = {
                "name": rec.name,
                "waybill_id": waybill.id,
                "lane_code": "clearance",
                "source_model": "operation.order.clearance",
                "source_id": rec.id,
                "is_main": False,
                "parent_card_id": main_card_map.get(rec.parent_id.id),
                "display_state": rec.state or "",
                "sequence": 20,
                "extra_data": {"bill_no": rec.waybill_id.bl_number or rec.waybill_id.hbl_number or rec.waybill_id.obl_number, "container_nums": rec.container_nums, "extra_reason": rec.extra_reason, "extra_remark": rec.extra_remark, "clearance_finish_datetime": fields.Datetime.to_string(rec.clearance_finish_datetime) if rec.clearance_finish_datetime else False},
                "active": True,
            }
            if key in source_map:
                env_card.browse(source_map[key]).write(vals)
            else:
                env_card.create(vals)
            seen.add(key)

        stale_ids = [rec.id for rec in existing if (rec.source_model, rec.source_id) not in seen]
        if stale_ids:
            env_card.browse(stale_ids).write({"active": False})

    @api.model
    def action_create_handover_from_waybill_lane(self, waybill_id):
        waybill = self.env["world.depot.waybill"].sudo().browse(waybill_id).exists()
        if not waybill:
            raise ValidationError(_("Waybill not found."))
        result = self.env["world.depot.waybill"].browse(waybill.id).action_workbench_create_handover()
        self.action_sync_cards_by_waybill(waybill.id)
        return result

    @api.model
    def action_open_clearance_wizard_from_waybill_lane(self, waybill_id):
        waybill = self.env["world.depot.waybill"].sudo().browse(waybill_id).exists()
        if not waybill:
            raise ValidationError(_("Waybill not found."))
        return self.env["world.depot.waybill"].browse(waybill.id).action_open_clearance_wizard_workbench()

    def action_card_create_child(self):
        self.ensure_one()
        if not self.is_main:
            raise ValidationError(_("Only main card can create child."))
        if self.lane_code == "handover" and self.source_model == "operation.order.handover":
            result = self.env["operation.order.handover"].browse(
                self.source_id).action_create_child_handover_workbench()
        elif self.lane_code == "clearance" and self.source_model == "operation.order.clearance":
            result = self.env["operation.order.clearance"].browse(
                self.source_id).action_create_child_clearance_workbench()
        else:
            raise ValidationError(_("This lane does not support child creation."))

        self.action_sync_cards_by_waybill(self.waybill_id.id)
        return result
