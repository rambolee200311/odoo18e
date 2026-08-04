# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class StockPicking(models.Model):
    _inherit = "stock.picking"

    is_pda_internal_transfer = fields.Boolean(string="PDA Internal Transfer", default=False, copy=False, index=True)
    pda_destination_location_id = fields.Many2one("stock.location", string="PDA Destination Location", domain="[('usage', '=', 'internal')]", copy=False, index=True, check_company=True)
    package_scan_lines = fields.One2many("stock.picking.package.scan", "picking_id", string="Package Scan Lines", copy=False)

    @api.model
    def action_create_pda_internal_transfer(self):
        picking_types = self.env["stock.picking.type"].sudo().search([
            ("name", "=", "Pallet Internal Transfers"),
            ("code", "=", "internal"),
            ("company_id", "=", self.env.company.id),
        ], limit=2)
        if not picking_types:
            raise UserError(_("PDA internal transfer operation type 'Pallet Internal Transfers' is not configured for the current company."))
        if len(picking_types) > 1:
            raise UserError(_("More than one PDA internal transfer operation type named 'Pallet Internal Transfers' exists for the current company."))
        picking_type = picking_types
        if not picking_type.default_location_src_id or not picking_type.default_location_dest_id:
            raise UserError(_("PDA internal transfer operation type must have default source and destination locations."))

        picking = self.create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": picking_type.default_location_dest_id.id,
            "is_pda_internal_transfer": True,
        })
        result = picking.get_pda_internal_transfer_scan_data()
        result.update({"success": True, "message": _("PDA internal transfer %s created.") % picking.name})
        return result

    def check_pda_internal_transfer_draft(self):
        self.ensure_one()
        if not self.is_pda_internal_transfer:
            raise UserError(_("This picking is not a PDA internal transfer."))
        if self.state != "draft":
            raise UserError(_("Only draft PDA internal transfers can be updated."))

    def get_pda_internal_transfer_scan_lines(self):
        self.ensure_one()
        return self.env["stock.picking.package.scan"].sudo().search([
            ("picking_id", "=", self.id),
        ], order="id desc")

    def check_pda_internal_transfer_location(self, location):
        self.ensure_one()
        if not location or location.usage != "internal":
            raise UserError(_("Destination location must be an internal location."))
        warehouse = self.picking_type_id.warehouse_id
        if not warehouse or not warehouse.view_location_id:
            raise UserError(_("PDA internal transfer operation type must belong to a warehouse."))
        warehouse_location = self.env["stock.location"].sudo().search([
            ("id", "=", location.id),
            ("id", "child_of", warehouse.view_location_id.id),
            ("usage", "=", "internal"),
        ], limit=1)
        if not warehouse_location:
            raise UserError(_("Location %s does not belong to the PDA internal transfer warehouse.") % location.display_name)
        return True

    def get_pda_package_quants(self, package):
        self.ensure_one()
        quants = self.env["stock.quant"].sudo().search([
            ("package_id", "=", package.id),
            ("company_id", "=", self.company_id.id),
            ("quantity", "!=", 0),
        ])
        if not quants:
            raise UserError(_("Package %s has no stock in the current company.") % (package.name or package.barcode))

        for quant in quants:
            rounding = quant.product_id.uom_id.rounding
            if quant.location_id.usage != "internal":
                raise UserError(_("Package %s contains stock outside an internal location.") % (package.name or package.barcode))
            if float_compare(quant.quantity, 0.0, precision_rounding=rounding) <= 0:
                raise UserError(_("Package %s contains invalid negative stock.") % (package.name or package.barcode))
            if not float_is_zero(quant.reserved_quantity, precision_rounding=rounding):
                raise UserError(_("Package %s has reserved stock.") % (package.name or package.barcode))

        source_locations = quants.location_id
        if len(source_locations) != 1:
            raise UserError(_("Package %s stock is split across multiple locations.") % (package.name or package.barcode))
        source_location = source_locations
        self.check_pda_internal_transfer_location(source_location)
        if self.pda_destination_location_id and source_location == self.pda_destination_location_id:
            raise UserError(_("Destination location is the same as the source location for package %s.") % (package.name or package.barcode))
        return quants

    def get_pda_internal_transfer_scan_data(self):
        results = []
        for rec in self:
            scan_lines = rec.get_pda_internal_transfer_scan_lines()
            destination_location = rec.pda_destination_location_id
            if rec.state == "done":
                next_step = "completed"
            elif destination_location:
                next_step = "scan_package"
            else:
                next_step = "scan_destination"
            results.append({
                "picking_id": rec.id,
                "picking_name": rec.name,
                "state": rec.state,
                "destination_location": {
                    "id": destination_location.id,
                    "name": destination_location.display_name,
                    "barcode": destination_location.barcode,
                } if destination_location else False,
                "package_scan_lines": [{
                    "id": scan_line.id,
                    "package_id": scan_line.package_id.id,
                    "package_name": scan_line.package_id.name or scan_line.package_id.barcode,
                    "barcode": scan_line.barcode,
                    "source_location": {
                        "id": scan_line.source_location_id.id,
                        "name": scan_line.source_location_id.display_name,
                        "barcode": scan_line.source_location_id.barcode,
                    },
                } for scan_line in scan_lines],
                "package_count": len(scan_lines),
                "next_step": next_step,
            })
        return results[0] if len(results) == 1 else results


    @api.model
    def cron_cancel_empty_pda_internal_transfers(self):
        expiration_datetime = fields.Datetime.now() - timedelta(hours=24)
        picking_ids = self.sudo().search([
            ("is_pda_internal_transfer", "=", True),
            ("state", "=", "draft"),
            ("package_scan_lines", "=", False),
            ("move_ids", "=", False),
            ("create_date", "<", expiration_datetime),
        ]).ids
        for rec in self.env["stock.picking"].browse(picking_ids):
            rec.action_cancel_pda_internal_transfer()
        return True


class StockPickingPackageScan(models.Model):
    _name = "stock.picking.package.scan"
    _description = "PDA Internal Transfer Package Scan"
    _order = "id desc"

    picking_id = fields.Many2one("stock.picking", string="Picking", required=True, ondelete="cascade", copy=False, index=True, check_company=True)
    package_id = fields.Many2one("stock.quant.package", string="Package", required=True, ondelete="restrict", copy=False, index=True, check_company=True)
    barcode = fields.Char(string="Package Barcode", required=True, copy=False, index=True)
    source_location_id = fields.Many2one("stock.location", string="Source Location", required=True, ondelete="restrict", copy=False, index=True, check_company=True)

    _sql_constraints = [
        ("unique_picking_package", "unique(picking_id, package_id)", "The same package can only be scanned once on an internal transfer."),
    ]

    @api.model_create_multi
    def create(self, values_list):
        if not self.env.context.get("allow_pda_package_scan"):
            raise UserError(_("Package scan records can only be created by PDA scanning."))
        return super().create(values_list)

    def write(self, values):
        raise UserError(_("Package scan records cannot be modified directly."))

    def unlink(self):
        if not self.env.context.get("allow_pda_package_reset"):
            raise UserError(_("Package scan records can only be removed by resetting the PDA internal transfer."))
        for rec in self:
            if rec.picking_id.state != "draft" or rec.picking_id.move_ids:
                raise UserError(_("Only draft PDA internal transfer scan records can be removed."))
        return super().unlink()
