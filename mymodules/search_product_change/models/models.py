from odoo import fields, models, _
from odoo.exceptions import ValidationError
from odoo.osv import expression
import re

class ProductTemplateBatchSearchWizard(models.TransientModel):
    _name = "product.template.batch.search.wizard"
    _description = "Product Template Batch Search Wizard"

    name_text = fields.Text(string="Product Names", required=True)

    def action_search(self):
        for rec in self:
            text = (rec.name_text or "").strip()
            if not text:
                raise ValidationError(_("Please paste product names (one per line)."))

            text = text.replace("\r\n", "\n").replace("\r", "\n")
            lines = [ln.replace("\u00a0", " ").strip() for ln in text.split("\n")]
            names = [ln for ln in lines if ln]
            names = [ln for ln in names if ln not in ("物料描述（长文本）", "物料描述(长文本)")]

            if not names:
                raise ValidationError(_("No valid product names found."))
            if len(names) > 200:
                raise ValidationError(_("Too many lines (%s). Please paste up to 200 lines at a time.") % len(names))

            # seen = set()
            domains = [[("name", "ilike", n)] for n in names]
            domain = expression.OR(domains) if domains else [("id", "=", 0)]

            rows = rec.env["product.template"].sudo().search_read(domain, ["id"])
            template_ids = [r["id"] for r in rows]

            kanban_view = rec.env.ref("product.product_template_kanban_view", raise_if_not_found=False)
            views = [(kanban_view.id, "kanban")] if kanban_view else []
            views += [(False, "form")]

            return {
                "type": "ir.actions.act_window",
                "name": _("Products"),
                "res_model": "product.template",
                "view_mode": "kanban,form",
                "views": views,
                "domain": [("id", "in", template_ids)] if template_ids else [("id", "=", 0)],
                "target": "current",
            }
