from odoo import api, fields, models
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta, time

class OperationWorkbenchDashboardData(models.Model):
    _name = "operation.workbench.dashboard.data"
    _description = "Operation Workbench Dashboard Data"
    _order = "id desc"
    _sql_constraints = [("uniq_lane_code", "unique(lane_code)", "Lane must be unique.")]

    name = fields.Char(string="Name", required=True, index=True, copy=False)
    lane_code = fields.Selection([("waybill", "Waybill"), ("handover", "Handover"), ("clearance", "Clearance")], string="Lane", required=True, index=True)
    near_due_count = fields.Integer(string="Near Due Count", default=0)
    overdue_count = fields.Integer(string="Overdue Count", default=0)
    record_ids_text = fields.Char(string="Record IDs (CSV)", help="Example: 11,12,13")

    @api.model
    def get_dashboard_counts(self):
        waybill_near_count = len(self.get_waybill_near_ids())
        handover_near_count = len(self.get_handover_near_ids())
        clearance_near_count = len(self.get_clearance_near_ids())

        waybill_overdue_count = len(self.get_waybill_overdue_ids())
        handover_overdue_count = len(self.get_handover_overdue_ids())
        clearance_overdue_count = len(self.get_clearance_overdue_ids())

        total_near_count = waybill_near_count + handover_near_count + clearance_near_count
        total_overdue_count = waybill_overdue_count + handover_overdue_count + clearance_overdue_count

        return {
            "waybill": {"near_due_count": waybill_near_count, "overdue_count": waybill_overdue_count},
            "handover": {"near_due_count": handover_near_count, "overdue_count": handover_overdue_count},
            "clearance": {"near_due_count": clearance_near_count, "overdue_count": clearance_overdue_count},
            "total": {"near_due_count": total_near_count, "overdue_count": total_overdue_count},
        }


    @api.model
    def get_lane_record_ids(self, lane_code, alert_type="overdue"):
        if lane_code not in ("waybill", "handover", "clearance"):
            raise ValidationError("Unsupported lane code.")
        if alert_type not in ("near", "overdue", "all"):
            raise ValidationError("Unsupported alert type.")

        lane_method_map = {
            "waybill": {
                "near": self.get_waybill_near_ids,
                "overdue": self.get_waybill_overdue_ids,
            },
            "handover": {
                "near": self.get_handover_near_ids,
                "overdue": self.get_handover_overdue_ids,
            },
            "clearance": {
                "near": self.get_clearance_near_ids,
                "overdue": self.get_clearance_overdue_ids,
            },
        }

        near_ids = lane_method_map[lane_code]["near"]()
        overdue_ids = lane_method_map[lane_code]["overdue"]()

        if alert_type == "near":
            ids_list = near_ids
        elif alert_type == "overdue":
            ids_list = overdue_ids
        else:
            ids_list = sorted(set(near_ids + overdue_ids), reverse=True)

        return {
            "lane_code": lane_code,
            "alert_type": alert_type,
            "near_due_count": len(near_ids),
            "overdue_count": len(overdue_ids),
            "ids": ids_list,
        }

    @api.model
    def to_date_value(self, value):
        if not value:
            return False
        if isinstance(value, str):
            return fields.Date.from_string(value)
        return value

    @api.model
    def to_datetime_value(self, value):
        if not value:
            return False
        if isinstance(value, str):
            return fields.Datetime.from_string(value)
        return value

    @api.model
    def get_now_datetime(self):
        now_value = fields.Datetime.now()
        return self.to_datetime_value(now_value)

    @api.model
    def get_base_datetime_from_waybill(self, waybill):
        base_date = self.to_date_value(waybill.ata) or self.to_date_value(waybill.eta)
        if not base_date:
            return False
        return datetime.combine(base_date, time(23, 59, 59))

    @api.model
    def get_alert_rule_values(self):
        env_rule = self.env["operation.workbench.alert.rule"]
        return env_rule.get_rule_values(company_id=self.env.company.id)

    @api.model
    def get_waybill_near_ids(self):
        env_waybill = self.env["world.depot.waybill"]
        rule = self.get_alert_rule_values()
        now_dt = self.get_now_datetime()
        near_hours = rule["arrival_near_hours"]

        rows = env_waybill.sudo().search([
            ("eta", "!=", False),
            ("ata", "=", False),
            ("state", "not in", ["new","done", "cancel"]),
        ], order="id desc")

        ids_list = []
        for rec in rows:
            eta_date = self.to_date_value(rec.eta)
            if not eta_date:
                continue
            eta_dt = datetime.combine(eta_date, time(23, 59, 59))
            near_start = eta_dt - timedelta(hours=near_hours)
            if near_start <= now_dt < eta_dt:
                ids_list.append(rec.id)
        return ids_list

    @api.model
    def get_handover_near_ids(self):
        env_handover = self.env["operation.order.handover"]
        rule = self.get_alert_rule_values()
        now_dt = self.get_now_datetime()

        available_days = rule["handover_available_days"]
        near_hours = rule["handover_near_hours"]
        done_states = ["released", "close", "cancelled"]

        rows = env_handover.sudo().search([
            ("waybill_id", "!=", False),
            ("state", "not in", done_states),
        ], order="id desc")

        ids_list = []
        for rec in rows:
            base_dt = self.get_base_datetime_from_waybill(rec.waybill_id)
            if not base_dt:
                continue
            due_dt = base_dt + timedelta(days=available_days)
            near_start = due_dt - timedelta(hours=near_hours)
            if near_start <= now_dt < due_dt:
                ids_list.append(rec.id)
        return ids_list

    @api.model
    def get_clearance_near_ids(self):
        env_clearance = self.env["operation.order.clearance"]
        rule = self.get_alert_rule_values()
        now_dt = self.get_now_datetime()

        available_days = rule["clearance_available_days"]
        near_hours = rule["clearance_near_hours"]
        done_states = ["clearanced", "close", "cancelled"]

        rows = env_clearance.sudo().search([
            ("waybill_id", "!=", False),
            ("state", "not in", done_states),
        ], order="id desc")

        ids_list = []
        for rec in rows:
            base_dt = self.get_base_datetime_from_waybill(rec.waybill_id)
            if not base_dt:
                continue
            due_dt = base_dt + timedelta(days=available_days)
            near_start = due_dt - timedelta(hours=near_hours)
            if near_start <= now_dt < due_dt:
                ids_list.append(rec.id)
        return ids_list


    @api.model
    def get_waybill_overdue_ids(self):
        env_waybill = self.env["world.depot.waybill"]
        now_dt = self.get_now_datetime()

        rows = env_waybill.sudo().search([
            ("eta", "!=", False),
            ("state", "not in", ["new", "done", "cancel"]),
        ], order="id desc")

        ids_list = []
        for rec in rows:
            eta_date = self.to_date_value(rec.eta)
            if not eta_date:
                continue
            eta_dt = datetime.combine(eta_date, time(23, 59, 59))

            ata_date = self.to_date_value(rec.ata)
            if ata_date:
                ata_dt = datetime.combine(ata_date, time(23, 59, 59))
                if ata_dt > eta_dt:
                    ids_list.append(rec.id)
            else:
                if now_dt >= eta_dt:
                    ids_list.append(rec.id)
        return ids_list

    @api.model
    def get_handover_overdue_ids(self):
        env_handover = self.env["operation.order.handover"]
        rule = self.get_alert_rule_values()
        now_dt = self.get_now_datetime()

        available_days = rule["handover_available_days"]
        done_states = ["released", "close", "cancelled"]

        rows = env_handover.sudo().search([
            ("waybill_id", "!=", False),
            ("state", "not in", done_states),
        ], order="id desc")

        ids_list = []
        for rec in rows:
            base_dt = self.get_base_datetime_from_waybill(rec.waybill_id)
            if not base_dt:
                continue
            due_dt = base_dt + timedelta(days=available_days)
            if now_dt >= due_dt:
                ids_list.append(rec.id)
        return ids_list

    @api.model
    def get_clearance_overdue_ids(self):
        env_clearance = self.env["operation.order.clearance"]
        rule = self.get_alert_rule_values()
        now_dt = self.get_now_datetime()

        available_days = rule["clearance_available_days"]
        done_states = ["clearanced", "close", "cancelled"]

        rows = env_clearance.sudo().search([
            ("waybill_id", "!=", False),
            ("state", "not in", done_states),
        ], order="id desc")

        ids_list = []
        for rec in rows:
            base_dt = self.get_base_datetime_from_waybill(rec.waybill_id)
            if not base_dt:
                continue
            due_dt = base_dt + timedelta(days=available_days)
            if now_dt >= due_dt:
                ids_list.append(rec.id)
        return ids_list

