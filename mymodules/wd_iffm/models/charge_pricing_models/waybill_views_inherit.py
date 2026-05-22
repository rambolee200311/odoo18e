from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class WaybillViewsInherit(models.Model):
    _inherit = 'world.depot.waybill'


    #一个模型看板打开动作
    def action_open_workbench_board_card(self):
        self.ensure_one()
        self.env["operation.workbench.card"].action_sync_cards_by_waybill(self.id)
        lane_waybill = self.env["operation.workbench.lane"].search([("code", "=", "waybill")], limit=1)
        ctx = {
            "default_waybill_id": self.id,
            "group_by": "lane_id",
        }
        if lane_waybill:
            ctx["default_lane_id"] = lane_waybill.id
        return {
            "type": "ir.actions.act_window",
            "name": _("Waybill Workbench"),
            "res_model": "operation.workbench.card",
            "view_mode": "kanban",
            "domain": [("waybill_id", "=", self.id), ("active", "=", True)],
            "context": ctx,
            "target": "current",
        }

    def action_open_workbench(self):
        self.ensure_one()
        return self.action_open_workbench_board_card()


    def action_model_form_views(self):
        self.ensure_one()
        model_name = self.env.context.get("open_model") or self._name
        res_id = self.env.context.get("open_res_id") or self.id
        view_id = self.env.context.get("open_view_id")
        return {
            "type": "ir.actions.act_window",
            "res_model": model_name,
            "res_id": res_id,
            "view_mode": "form",
            "views": [(view_id, "form")] if view_id else [(False, "form")],
            "target": "current",
        }



    @api.model
    def serialize_handover_master(self, rec):
        rec.ensure_one()
        return {
            "id": rec.id,
            "name": rec.name,
            "state": rec.state,
            "waybill_id": rec.waybill_id.id if rec.waybill_id else False,
            "bill_no": rec.bl_number or rec.hbl_number or rec.obl_number,
            "do_issue_datetime": fields.Datetime.to_string(rec.do_issue_datetime) if rec.do_issue_datetime else False,
            "container_nums": rec.container_nums,
        }

    @api.model
    def serialize_handover_child(self, rec):
        rec.ensure_one()
        return {
            "id": rec.id,
            "name": rec.name,
            "state": rec.state,
            "waybill_id": rec.waybill_id.id if rec.waybill_id else False,
            "parent_id": rec.parent_id.id if rec.parent_id else False,
            "is_child": True,
            "extra_reason": rec.extra_reason or False,
            "actual_datetime": fields.Datetime.to_string(rec.actual_datetime) if rec.actual_datetime else False,
            "extra_remark": rec.extra_remark or "",
            "bill_no": rec.bl_number or rec.hbl_number or rec.obl_number,
            "do_issue_datetime": fields.Datetime.to_string(rec.do_issue_datetime) if rec.do_issue_datetime else False,
            "container_nums": rec.container_nums,
        }

    @api.model
    def serialize_clearance_master(self, rec):
        rec.ensure_one()
        return {
            "id": rec.id,
            "name": rec.name,
            "state": rec.state,
            "waybill_id": rec.waybill_id.id if rec.waybill_id else False,
            "bill_no": rec.waybill_id.bl_number or rec.waybill_id.hbl_number or rec.waybill_id.obl_number,
            "clearance_finish_datetime": fields.Datetime.to_string(rec.clearance_finish_datetime) if rec.clearance_finish_datetime else False,
            "container_nums": rec.container_nums,
        }

    @api.model
    def serialize_clearance_child(self, rec):
        rec.ensure_one()
        return {
            "id": rec.id,
            "name": rec.name,
            "state": rec.state,
            "waybill_id": rec.waybill_id.id if rec.waybill_id else False,
            "parent_id": rec.parent_id.id if rec.parent_id else False,
            "is_child": True,
            "extra_reason": rec.extra_reason or False,
            "actual_datetime": fields.Datetime.to_string(rec.actual_datetime) if rec.actual_datetime else False,
            "extra_remark": rec.extra_remark or "",
            "bill_no": rec.waybill_id.bl_number or rec.waybill_id.hbl_number or rec.waybill_id.obl_number,
            "clearance_finish_datetime": fields.Datetime.to_string(
                rec.clearance_finish_datetime) if rec.clearance_finish_datetime else False,
            "container_nums": rec.container_nums,
        }

    @api.model
    def get_workbench_data(self, waybill_id):
        waybill_model = self.env["world.depot.waybill"]
        handover_model = self.env["operation.order.handover"]
        clearance_model = self.env["operation.order.clearance"]

        waybill = waybill_model.sudo().browse(waybill_id).exists()
        if not waybill:
            raise ValidationError(_("Waybill not found."))


        handover_roots = handover_model.sudo().search(
            [("waybill_id", "=", waybill.id), ("parent_id", "=", False), ("state", "!=", "cancelled")],
            order="id desc",
        )
        handover_master = handover_roots[:1]
        handover_children = handover_model.sudo().search(
            [("parent_id", "=", handover_master.id), ("state", "!=", "cancelled")],
            order="id desc",
        ) if handover_master else handover_model.browse()

        clearance_roots = clearance_model.sudo().search(
            [("waybill_id", "=", waybill.id), ("parent_id", "=", False), ("state", "!=", "cancelled")],
            order="id desc",
        )
        clearance_children = clearance_model.sudo().search(
            [("parent_id", "in", clearance_roots.ids), ("state", "!=", "cancelled")],
            order="id desc",
        ) if clearance_roots else clearance_model.browse()

        children_map = {}
        for rec in clearance_children:
            parent_id = rec.parent_id.id
            children_map.setdefault(parent_id, [])
            children_map[parent_id].append(self.serialize_clearance_child(rec))

        clearance_masters = []
        for rec in clearance_roots:
            clearance_masters.append({
                "master": self.serialize_clearance_master(rec),
                "children": children_map.get(rec.id, []),
            })


        waybill_container_ids = set(waybill.container_ids.ids)

        clearance_all = clearance_model.sudo().search([
            ("waybill_id", "=", waybill.id),
            ("state", "!=", "cancelled"),
        ])
        clearance_container_ids = set(clearance_all.mapped("clearance_container_ids").ids)

        unassigned_container_ids = waybill_container_ids - clearance_container_ids
        has_unassigned_container = bool(unassigned_container_ids)
        return {
            "waybill": {
                "id": waybill.id,
                "billno": waybill.billno,
                "bl_number": waybill.bl_number,
                "hbl_number": waybill.hbl_number,
                "container_number": ', '.join( [line.container_number for line in waybill.container_ids]),
                "state": waybill.state,
            },
            "handover": {
                "master": self.serialize_handover_master(handover_master) if handover_master else False,
                "children": [self.serialize_handover_child(rec) for rec in handover_children],
                "master_count": len(handover_roots),

                "can_create_master": waybill.state == "confirm" and waybill.is_arrived == True and not bool(handover_master),
            },
            "clearance": {
                "masters": clearance_masters,
                "master_count": len(clearance_roots),
                "can_create_master": waybill.state == "confirm" and waybill.is_arrived and has_unassigned_container,
            },
        }


    def action_open_form(self):
        self.ensure_one()
        form_view_ref = self.env.context.get('form_view_ref', False)
        views = [[False, 'form']]
        if form_view_ref:
            view_id = self.env.ref(form_view_ref).id
            views = [[view_id, 'form']]
        return {
            'type': 'ir.actions.act_window',
            'name': 'Waybill Form',
            'res_model': 'world.depot.waybill',
            'res_id': self.id,
            'view_mode': 'form',
            'views': views,
            'target': 'current',
        }


    def action_workbench_create_handover(self):
        env_handover = self.env["operation.order.handover"]
        result = []

        for rec in self:
            if rec.state == "done":
                raise UserError(_("This waybill has been done. Formal order replacement operations cannot be created."))
            if rec.state != "confirm":
                raise ValidationError(_("Only confirmed waybills can create handover orders."))
            if not env_handover.check_access_rights("create", raise_exception=False):
                raise ValidationError(_("You do not have permission to create handover orders."))

            main_count = env_handover.sudo().search_count([
                ("waybill_id", "=", rec.id),
                ("parent_id", "=", False),
                ("state", "!=", "cancelled"),
            ])
            if main_count:
                raise ValidationError(_("Main handover already exists."))

            attachment_lines = [(0, 0, {
                "doc_type": line.bill_doc_type,
                "remark": line.description,
                "file": line.file,
                "name": line.filename,
            }) for line in rec.other_docs_ids]

            charge_lines = [(0, 0, {
                "charge_item_id": line.charge_item_id.id,
                "charge_origin_type": "quotation",
                "unit_price": line.unit_price,
                "is_fixed_fee": line.is_fixed_fee,
            }) for line in rec.project.quotation_id.quotation_thc_lines] if rec.project and rec.project.quotation_id else []

            handover = env_handover.create({
                "waybill_id": rec.id,
                "project_id": rec.project.id if rec.project else False,
                "shipping_line_id": rec.shipping.id if rec.shipping else False,
                "container_qty": rec.container_qty,
                "attachment_line_ids": attachment_lines,
                "charge_line_ids": charge_lines,
            })
            rec.write({"handover_id": handover.id})

            result.append({
                "waybill_id": rec.id,
                "handover_id": handover.id,
                "handover_name": handover.name,
                "container_qty": handover.container_qty,
                "message": _("Handover order created successfully."),
            })

        return result[0] if len(result) == 1 else result

    def action_open_clearance_wizard_workbench(self):
        self.ensure_one()
        if self.state == "done":
            raise UserError(_("This waybill has been done. Formal order replacement operations cannot be created."))
        if self.state != "confirm":
            raise UserError(_("Please change the waybill status to confirm first."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Select Containers"),
            "res_model": "waybill.create.clearance.wizard",
            "view_mode": "form",
            "views": [(self.env.ref("wd_iffm.view_waybill_create_clearance_wizard_form").id, "form")],
            "target": "new",
            "context": {
                "active_model": "world.depot.waybill",
                "active_id": self.id,
                "default_waybill_id": self.id,
                "from_workbench": True,
            },
        }



    def action_workbench_create_clearance(self):
        env_clearance = self.env["operation.order.clearance"]
        result = []

        for rec in self:
            if rec.state == "done":
                raise UserError(_("This waybill has been done. Formal order replacement operations cannot be created."))
            if rec.state != "confirm":
                raise ValidationError(_("Only confirmed waybills can create clearance orders."))
            if not env_clearance.check_access_rights("create", raise_exception=False):
                raise ValidationError(_("You do not have permission to create clearance orders."))

            main_count = env_clearance.sudo().search_count([
                ("waybill_id", "=", rec.id),
                ("parent_id", "=", False),
                ("state", "!=", "cancelled"),
            ])
            if main_count:
                raise ValidationError(_("Main clearance already exists."))

            attachment_lines = [(0, 0, {
                "doc_type": line.bill_doc_type,
                "remark": line.description,
                "file": line.file,
                "name": line.filename,
            }) for line in rec.other_docs_ids]

            charge_lines = [(0, 0, {
                "charge_item_id": line.charge_item_id.id,
                "charge_origin_type": "quotation",
                "unit_price": line.unit_price,
                "is_fixed_fee": line.is_fixed_fee,
            }) for line in rec.project.quotation_id.quotation_customs_lines] if rec.project and rec.project.quotation_id else []

            clearance = env_clearance.create({
                "waybill_id": rec.id,
                "project_id": rec.project.id if rec.project else False,
                "shipping_line_id": rec.shipping.id if rec.shipping else False,
                "handover_id": rec.handover_id.id if rec.handover_id else False,
                "container_qty": rec.container_qty,
                "clearance_container_ids": [(6, 0, rec.container_ids.ids)],
                "attachment_line_ids": attachment_lines,
                "charge_line_ids": charge_lines,
            })
            rec.write({"clearance_id": clearance.id})

            result.append({
                "waybill_id": rec.id,
                "clearance_id": clearance.id,
                "clearance_name": clearance.name,
                "container_qty": clearance.container_qty,

                "message": _("Clearance order created successfully."),
            })

        return result[0] if len(result) == 1 else result