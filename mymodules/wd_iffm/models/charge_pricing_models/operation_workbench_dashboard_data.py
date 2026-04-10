# models/operation_workbench_dashboard_data.py
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class OperationWorkbenchDashboardData(models.Model):
    _name = "operation.workbench.dashboard.data"
    _description = "Operation Workbench Dashboard Data"
    _order = "id desc"

    name = fields.Char(string="Name", required=True, index=True, copy=False)
    lane_code = fields.Selection([("waybill", "Waybill"), ("handover", "Handover"), ("clearance", "Clearance")], string="Lane", required=True, index=True)
    near_due_count = fields.Integer(string="Near Due Count", default=0)
    overdue_count = fields.Integer(string="Overdue Count", default=0)
    record_ids_text = fields.Char(string="Record IDs (CSV)", help="Example: 11,12,13")

    _sql_constraints = [("uniq_lane_code", "unique(lane_code)", "Lane must be unique.")]

    @api.model
    def parse_ids_text(self, text_value):
        if not text_value:
            return []
        result = []
        for part in str(text_value).split(","):
            part = part.strip()
            if not part:
                continue
            if part.isdigit():
                result.append(int(part))
        return result

    @api.model
    def get_dashboard_counts(self):
        env_data = self.env["operation.workbench.dashboard.data"]
        rows = env_data.sudo().search_read(["lane_code", "near_due_count", "overdue_count"], order="id desc")
        data = {
            "waybill": {"near_due_count": 0, "overdue_count": 0},
            "handover": {"near_due_count": 0, "overdue_count": 0},
            "clearance": {"near_due_count": 0, "overdue_count": 0},
            "total": {"near_due_count": 0, "overdue_count": 0},
        }
        for row in rows:
            code = row.get("lane_code")
            if code in ("waybill", "handover", "clearance"):
                near_v = row.get("near_due_count") or 0
                over_v = row.get("overdue_count") or 0
                data[code]["near_due_count"] = near_v
                data[code]["overdue_count"] = over_v
                data["total"]["near_due_count"] += near_v
                data["total"]["overdue_count"] += over_v
        return data

    @api.model
    def get_lane_record_ids(self, lane_code):
        if lane_code not in ("waybill", "handover", "clearance"):
            raise ValidationError("Unsupported lane code.")
        env_data = self.env["operation.workbench.dashboard.data"]
        rec = env_data.sudo().search([("lane_code", "=", lane_code)], limit=1)
        return {
            "lane_code": lane_code,
            "near_due_count": rec.near_due_count if rec else 0,
            "overdue_count": rec.overdue_count if rec else 0,
            "ids": self.parse_ids_text(rec.record_ids_text if rec else ""),
        }
