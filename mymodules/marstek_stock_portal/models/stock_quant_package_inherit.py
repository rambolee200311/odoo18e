# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.osv import expression

from .utils import (
    portal_apply_date_filters,
    portal_location_is_allowed,
    portal_package_container_from_name,
    portal_package_ids_by_shipping,
    portal_package_shipping_map,
    portal_product_name,
    portal_quant_domain,
    portal_stock_rows_from_quants,
)


class StockQuantPackage(models.Model):
    _inherit = "stock.quant.package"

    container_no = fields.Char(string="Container No", compute="_compute_marstek_shipping_info", search="search_container_no")
    bl_no = fields.Char(string="Bill of Lading", compute="_compute_marstek_shipping_info", search="search_bl_no")

    @api.depends("name", "quant_ids.lot_id.cntrno", "quant_ids.lot_id.bill_of_lading")
    def _compute_marstek_shipping_info(self):
        info_by_package = portal_package_shipping_map(self.env, self.ids)
        for rec in self:
            info = info_by_package.get(rec.id, {})
            rec.container_no = info.get("container_no") or portal_package_container_from_name(rec.name)
            rec.bl_no = info.get("bl_no") or ""

    @api.model
    def search_container_no(self, operator, value):
        package_ids = portal_package_ids_by_shipping(self.env, "container_no", operator, value)
        return [("id", "in", package_ids)] if package_ids else [("id", "=", 0)]

    @api.model
    def search_bl_no(self, operator, value):
        package_ids = portal_package_ids_by_shipping(self.env, "bl_no", operator, value)
        return [("id", "in", package_ids)] if package_ids else [("id", "=", 0)]

    @api.model
    def get_all_stock(self, filters=None, offset=0, limit=0):
        filters = filters or {}
        domain = portal_quant_domain(self.env)
        container_no = filters.get("container_no")
        bl_no = filters.get("bl_no")
        product_code = filters.get("product_code")
        location_id = filters.get("location_id")
        stock_group_mode = filters.get("stock_group_mode")
        if container_no:
            package_ids = portal_package_ids_by_shipping(self.env, "container_no", "ilike", container_no)
            if not package_ids:
                return []
            domain.append(("package_id", "in", package_ids))
        if bl_no:
            package_ids = portal_package_ids_by_shipping(self.env, "bl_no", "ilike", bl_no)
            if not package_ids:
                return []
            domain.append(("package_id", "in", package_ids))
        if product_code:
            product_domain = ["|", ("product_id.default_code", "ilike", product_code), ("product_id.barcode", "ilike", product_code)]
            domain = expression.AND([domain, product_domain])
        if location_id:
            if not portal_location_is_allowed(self.env, location_id):
                return []
            domain.append(("location_id", "child_of", int(location_id)))
        portal_apply_date_filters(domain, filters, "in_date", ("date_from",), ("date_to",))
        quant_env = self.env["stock.quant"].sudo()
        quants = quant_env.search(domain, order="in_date desc, id desc", offset=offset, limit=limit)
        if stock_group_mode == "package":
            info_by_package = portal_package_shipping_map(self.env, quants.mapped("package_id").ids)
            rows_by_key = {}
            for quant in quants:
                package = quant.package_id
                product = quant.product_id
                location = quant.location_id
                key = (location.id, package.id)
                row = rows_by_key.setdefault(key, {
                    "package_id": package.id,
                    "package_name": package.name or "",
                    "container_no": info_by_package.get(package.id, {}).get("container_no") or "",
                    "bl_no": info_by_package.get(package.id, {}).get("bl_no") or "",
                    "location_id": location.id,
                    "location_name": location.complete_name or location.display_name or "",
                    "total_quantity": 0.0,
                    "product_lines": {},
                })
                product_key = (product.id, product.uom_id.id)
                product_line = row["product_lines"].setdefault(product_key, {
                    "product_code": product.barcode or product.default_code or "",
                    "product_name": portal_product_name(product),
                    "uom_name": product.uom_id.name or "",
                    "quantity": 0.0,
                })
                product_line["quantity"] += quant.quantity
                row["total_quantity"] += quant.quantity
            rows = list(rows_by_key.values())
            for row in rows:
                row["product_lines"] = list(row["product_lines"].values())
                row["product_count"] = len(row["product_lines"])
                row["product_summary"] = ", ".join(
                    "%s × %s" % (product_line["product_name"], product_line["quantity"])
                    for product_line in row["product_lines"]
                )
            return rows
        return portal_stock_rows_from_quants(self.env, quants)

    @api.model
    def get_stock_by_container_no(self, container_no):
        result = {"container_no": container_no or "", "bl_no": "", "total_quantity": 0.0, "lines": []}
        if not container_no:
            return result
        package_ids = portal_package_ids_by_shipping(self.env, "container_no", "=", container_no)
        if not package_ids:
            package_ids = portal_package_ids_by_shipping(self.env, "container_no", "ilike", container_no)
        if not package_ids:
            return result
        domain = portal_quant_domain(self.env)
        domain.append(("package_id", "in", package_ids))
        quant_env = self.env["stock.quant"].sudo()
        quants = quant_env.search(domain, order="in_date desc, id desc")
        lines = portal_stock_rows_from_quants(self.env, quants, forced_container_no=container_no)
        result["lines"] = lines
        result["total_quantity"] = sum(line["quantity"] for line in lines)
        result["bl_no"] = next((line["bl_no"] for line in lines if line["bl_no"]), "")
        return result
