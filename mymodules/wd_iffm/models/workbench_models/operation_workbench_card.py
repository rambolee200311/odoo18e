from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.addons.wd_iffm.models.charge_pricing_models.waybill import WAYBILL_STATE
from odoo.addons.wd_iffm.models.clearance_models.operation_order_clearance import CLEARANCE_STATE
from odoo.addons.wd_iffm.models.handover_models.operation_order_handover import HANDOVER_STATE

def _safe_process_ondelete_patch():
    """
    Patch IrModelFieldsSelection._process_ondelete to safely skip fields
    that don't have an 'ondelete' attribute (e.g., Char, Text fields).
    This fixes AttributeError when stale ir_model_fields_selection rows
    exist in the database for non-relational fields.
    """
    from odoo.addons.base.models.ir_model import IrModelSelection
    original = IrModelSelection._process_ondelete

    def safe_process_ondelete(self):
        def safe_write(records, fname, value):
            if not records:
                return
            try:
                with self.env.cr.savepoint():
                    records.write({fname: value})
            except Exception:
                pass

        for selection in self:
            Model = self.env.get(selection.field_id.model)
            if Model is None:
                continue
            field = Model._fields.get(selection.field_id.name)
            if not field or not field.store or not Model._auto:
                continue

            # Fields without 'ondelete' (Char, Text, etc.) cannot have selection
            # ondelete policies; skip them to avoid AttributeError
            if not hasattr(field, 'ondelete'):
                continue

            ondelete = (field.ondelete or {}).get(selection.value)
            if ondelete is None and field.manual and not field.required:
                ondelete = 'set null'
            if ondelete is None:
                continue
            elif callable(ondelete):
                ondelete(selection._get_records())
            elif ondelete == 'set null':
                safe_write(selection._get_records(), field.name, False)
            elif ondelete == 'set default':
                value = field.convert_to_write(field.default(Model), Model)
                safe_write(selection._get_records(), field.name, value)
            elif ondelete.startswith('set '):
                safe_write(selection._get_records(), field.name, ondelete[4:])
            elif ondelete == 'cascade':
                selection._get_records().unlink()

    IrModelSelection._process_ondelete = safe_process_ondelete


_safe_process_ondelete_patch()


class OperationWorkbenchCard(models.Model):
    _name = "operation.workbench.card"
    _description = "Operation Workbench Card"
    _order = "id asc"

    name = fields.Char(string="Card Name", required=True, index=True, copy=False)
    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True, index=True, ondelete="cascade")
    lane_id = fields.Many2one(
        "operation.workbench.lane",
        string="Lane",
        required=True,
        ondelete="restrict",
        index=True,
        group_expand="_read_group_lane_ids",
    )
    lane_code = fields.Char(string="Lane Code", related="lane_id.code", store=True, readonly=True)
    source_model = fields.Char(string="Source Model", required=True, index=True)
    source_id = fields.Integer(string="Source ID", required=True, index=True)
    is_main = fields.Boolean(string="Is Main", default=False, index=True)
    parent_card_id = fields.Many2one("operation.workbench.card", string="Parent Card", index=True, ondelete="set null")
    child_lines = fields.One2many("operation.workbench.card", "parent_card_id", string="Child Cards")
    display_state = fields.Char(string="Display State", index=True)

    waybill_state = fields.Selection(string="Waybill State", selection=WAYBILL_STATE)
    handover_state = fields.Selection(string="Handover State", selection=HANDOVER_STATE)
    clearance_state = fields.Selection(string="Clearance State", selection=CLEARANCE_STATE)

    sequence = fields.Integer(string="Sequence", default=10, index=True)
    extra_data = fields.Json(string="Extra Data")
    active = fields.Boolean(string="Active", default=True, index=True)

    _sql_constraints = [
        ("uniq_workbench_source", "unique(source_model,source_id)", "Source model and source id must be unique."),
    ]

    @api.model
    def _read_group_lane_ids(self, lanes, domain):
        """Always show every active lane (like project.task stage group_expand)."""
        return lanes.search([("active", "=", True)], order="sequence asc, id asc")

    @api.constrains("waybill_id", "lane_id", "lane_code", "is_main", "active")
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
    def _lane_by_code(self, code):
        lane = self.env["operation.workbench.lane"].sudo().search([("code", "=", code)], limit=1)
        if not lane:
            raise ValidationError(_("Workbench lane with code %s is missing. Update module or create the lane.") % code)
        return lane

    @api.model
    def action_sync_cards_by_waybill(self, waybill_id):
        env_card = self.env["operation.workbench.card"]
        env_waybill = self.env["world.depot.waybill"]
        env_handover = self.env["operation.order.handover"]
        env_clearance = self.env["operation.order.clearance"]

        waybill = env_waybill.sudo().browse(waybill_id).exists()
        if not waybill:
            raise ValidationError(_("Waybill not found."))

        lane_waybill = self._lane_by_code("waybill")

        waybill_card = env_card.sudo().search(
            [("waybill_id", "=", waybill.id), ("lane_code", "=", "waybill"), ("active", "=", True)], limit=1
        )
        waybill_vals = {
            "name": waybill.bl_number or waybill.hbl_number or waybill.obl_number or str(waybill.id),
            "waybill_id": waybill.id,
            "lane_id": lane_waybill.id,
            "source_model": "world.depot.waybill",
            "source_id": waybill.id,
            "is_main": True,
            "display_state": waybill.state or "",
            "waybill_state": waybill.state or "",
            "sequence": 1,
            "extra_data": {
                "billno": waybill.billno,
                "bl_number": waybill.bl_number,
                "hbl_number": waybill.hbl_number,
                "mbl_number": waybill.obl_number,
                "container_qty":waybill.container_qty,
                "container_number": ", ".join([line.container_number for line in waybill.container_ids]),
            },
            "active": True,
        }
        if waybill_card:
            env_card.browse(waybill_card.id).write(waybill_vals)
        else:
            env_card.create(waybill_vals)

        handover_roots = env_handover.sudo().search(
            [("waybill_id", "=", waybill.id), ("parent_id", "=", False), ("state", "!=", "cancelled")], order="id desc"
        )
        handover_children = (
            env_handover.sudo().search([("parent_id", "in", handover_roots.ids), ("state", "!=", "cancelled")], order="id desc")
            if handover_roots
            else env_handover.browse()
        )
        self.action_sync_handover_cards(waybill, handover_roots, handover_children)

        clearance_roots = env_clearance.sudo().search(
            [("waybill_id", "=", waybill.id), ("parent_id", "=", False), ("state", "!=", "cancelled")], order="id desc"
        )
        clearance_children = (
            env_clearance.sudo().search([("parent_id", "in", clearance_roots.ids), ("state", "!=", "cancelled")], order="id desc")
            if clearance_roots
            else env_clearance.browse()
        )
        self.action_sync_clearance_cards(waybill, clearance_roots, clearance_children)
        return True

    @api.model
    def action_sync_handover_cards(self, waybill, root_lines, child_lines):
        env_card = self.env["operation.workbench.card"]
        lane_handover = self._lane_by_code("handover")
        existing = env_card.sudo().search([("waybill_id", "=", waybill.id), ("lane_code", "=", "handover"), ("active", "=", True)])
        source_map = {(rec.source_model, rec.source_id): rec.id for rec in existing}
        main_card_map = {}
        seen = set()

        for rec in root_lines:
            key = ("operation.order.handover", rec.id)
            vals = {
                "name": rec.name,
                "waybill_id": waybill.id,
                "lane_id": lane_handover.id,
                "source_model": "operation.order.handover",
                "source_id": rec.id,
                "is_main": True,
                "parent_card_id": False,
                "display_state": rec.state or "",
                "handover_state": rec.state or "",
                "sequence": 10,
                "extra_data": {
                    "billno": waybill.billno,
                    "bl_number": waybill.bl_number,
                    "hbl_number": waybill.hbl_number,
                    "mbl_number": waybill.obl_number,
                    "container_qty": rec.container_qty,
                    "container_nums": rec.container_nums,
                    "do_issue_datetime": fields.Datetime.to_string(rec.do_issue_datetime) if rec.do_issue_datetime else False,
                },
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
                "lane_id": lane_handover.id,
                "source_model": "operation.order.handover",
                "source_id": rec.id,
                "is_main": False,
                "parent_card_id": main_card_map.get(rec.parent_id.id),
                "display_state": rec.state or "",
                "handover_state": rec.state or "",
                "sequence": 20,
                "extra_data": {
                    "billno": waybill.billno,
                    "bl_number": waybill.bl_number,
                    "hbl_number": waybill.hbl_number,
                    "mbl_number": waybill.obl_number,
                    "container_qty": rec.container_qty,
                    "container_nums": rec.container_nums,
                    "do_issue_datetime": fields.Datetime.to_string(rec.actual_datetime) if rec.actual_datetime else False,
                    "extra_reason": rec.extra_reason,
                    "extra_remark": rec.extra_remark,
                },
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
        lane_clearance = self._lane_by_code("clearance")
        existing = env_card.sudo().search([("waybill_id", "=", waybill.id), ("lane_code", "=", "clearance"), ("active", "=", True)])
        source_map = {(rec.source_model, rec.source_id): rec.id for rec in existing}
        main_card_map = {}
        seen = set()

        for rec in root_lines:
            key = ("operation.order.clearance", rec.id)
            vals = {
                "name": rec.name,
                "waybill_id": waybill.id,
                "lane_id": lane_clearance.id,
                "source_model": "operation.order.clearance",
                "source_id": rec.id,
                "is_main": True,
                "parent_card_id": False,
                "display_state": rec.state or "",
                "clearance_state": rec.state or "",
                "sequence": 10,
                "extra_data": {
                    "billno": waybill.billno,
                    "bl_number": waybill.bl_number,
                    "hbl_number": waybill.hbl_number,
                    "mbl_number": waybill.obl_number,
                    "container_qty": rec.container_qty,
                    "container_nums": rec.container_nums,
                    "clearance_finish_datetime": fields.Datetime.to_string(rec.clearance_finish_datetime)
                    if rec.clearance_finish_datetime
                    else False,
                },
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
                "lane_id": lane_clearance.id,
                "source_model": "operation.order.clearance",
                "source_id": rec.id,
                "is_main": False,
                "parent_card_id": main_card_map.get(rec.parent_id.id),
                "display_state": rec.state or "",
                "clearance_state": rec.state or "",
                "sequence": 20,
                "extra_data": {
                    "billno": waybill.billno,
                    "bl_number": waybill.bl_number,
                    "hbl_number": waybill.hbl_number,
                    "mbl_number": waybill.obl_number,
                    "container_qty": rec.container_qty,
                    "container_nums": rec.container_nums,
                    "extra_reason": rec.extra_reason,
                    "extra_remark": rec.extra_remark,
                    "clearance_finish_datetime": fields.Datetime.to_string(rec.clearance_finish_datetime)
                    if rec.clearance_finish_datetime
                    else False,
                },
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
            result = self.env["operation.order.handover"].browse(self.source_id).action_create_child_handover_workbench()
        elif self.lane_code == "clearance" and self.source_model == "operation.order.clearance":
            result = self.env["operation.order.clearance"].browse(self.source_id).action_create_child_clearance_workbench()
        else:
            raise ValidationError(_("This lane does not support child creation."))

        self.action_sync_cards_by_waybill(self.waybill_id.id)
        return result

    # 打开详情页
    def action_model_form_views(self):
        self.ensure_one()
        model_name = self.env.context.get("open_model") or self.source_model
        res_id = self.env.context.get("open_res_id") or self.source_id
        open_view_ref = self.env.context.get("open_view_ref")
        view_id = None
        if open_view_ref:
            view = self.env.ref(open_view_ref, raise_if_not_found=False)
            view_id = view.id if view else False
        if not model_name or not res_id:
            raise ValidationError(_("Source record is missing."))

        return {
            "type": "ir.actions.act_window",
            "res_model": model_name,
            "res_id": res_id,
            "view_mode": "form",
            "views": [(view_id, "form")] if view_id else [(False, "form")],
            "target": "current",
        }
