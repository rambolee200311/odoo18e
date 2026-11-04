import logging

from odoo import api, models


_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    @api.model
    def ensure_pda_internal_transfer_picking_type(self):
        company_records = self.env["res.company"].sudo().search([])
        picking_type_model = self.env["stock.picking.type"]
        warehouse_model = self.env["stock.warehouse"]
        for company in company_records:
            picking_types = picking_type_model.sudo().search([
                ("name", "=", "Pallet Internal Transfers"),
                ("code", "=", "internal"),
                ("company_id", "=", company.id),
            ], limit=2)
            if picking_types:
                if len(picking_types) > 1:
                    _logger.warning("PDA internal transfer picking type was not created for company %s because multiple matching operation types exist.", company.display_name)
                continue
            warehouse_records = warehouse_model.sudo().search([("company_id", "=", company.id), ("name", "=", "SPN-Malledijk 3h")], order="id", limit=1)
            if len(warehouse_records) != 1:
                _logger.warning("PDA internal transfer picking type was not created for company %s because warehouse SPN-Malledijk 3h was not found.", company.display_name)
                continue
            picking_type_model.with_company(company).create({
                "name": "Pallet Internal Transfers",
                "code": "internal",
                "sequence_code": "PDAINT",
                "warehouse_id": warehouse_records.id,
                "company_id": company.id,
                "show_entire_packs": True,
            })
