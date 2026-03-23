from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WaybillViewsInherit(models.Model):
    _inherit = 'world.depot.waybill'

    def action_open_workbench(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "waybill_workbench",
            "name": "Waybill Workbench",
            "params": {"waybill_id": self.id},
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

        # 换单：只允许 1 张主卡（取最新一张；多张时回传冲突信息）
        handover_roots = handover_model.sudo().search(
            [("waybill_id", "=", waybill.id), ("parent_id", "=", False), ("state", "!=", "cancelled")],
            order="id desc",
        )
        handover_master = handover_roots[:1]
        handover_children = handover_model.sudo().search(
            [("parent_id", "=", handover_master.id), ("state", "!=", "cancelled")],
            order="id desc",
        ) if handover_master else handover_model.browse()

        # 清关：允许多张主卡（每张主卡各自带子卡）
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