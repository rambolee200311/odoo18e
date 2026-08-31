# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.osv import expression

from .utils import (
    portal_apply_date_filters,
    portal_filter_value,
    portal_format_datetime,
    portal_project_domain,
)


class InboundOrder(models.Model):
    _inherit = "world.depot.inbound.order"

    @api.model
    def get_inbound_list(self, filters=None, offset=0, limit=0):
        filters = filters or {}
        domain = portal_project_domain(self.env, "project")
        inbound_no = portal_filter_value(filters, "inbound_no", "reference")
        container_no = filters.get("container_no")
        bl_no = filters.get("bl_no")
        portal_inbound_status = filters.get("portal_inbound_status")
        domain.append(("state", "=", "confirm"))
        if inbound_no:
            domain = expression.AND([domain, ["|", ("billno", "ilike", inbound_no), ("reference", "ilike", inbound_no)]])
        if bl_no:
            domain.append(("bl_no", "ilike", bl_no))
        if container_no:
            domain.append(("cntr_no", "ilike", container_no))

        if portal_inbound_status == "inbound_confirmed":
            domain.append(("stock_picking_id", "=", False))
        elif portal_inbound_status == "inbound_processing":
            domain += [("stock_picking_id", "!=", False), ("stock_picking_id.state", "!=", "done")]
        elif portal_inbound_status == "inbound_done":
            domain.append(("stock_picking_id.state", "=", "done"))

        portal_apply_date_filters(domain, filters, "i_datetime", ("inbound_date_from",), ("inbound_date_to",))
        inbound_env = self.env["world.depot.inbound.order"].sudo()
        orders = inbound_env.search(domain, order="i_datetime desc, a_date desc, date desc, id desc", offset=offset, limit=limit)
        rows = []
        for rec in orders:
            picking = rec.stock_picking_id
            if picking and picking.state == "done":
                state = "inbound_done"
            elif picking:
                state = "inbound_processing"
            else:
                state = "inbound_confirmed"

            total_quantity = sum(line.quantity for line in rec.inbound_order_product_ids)
            total_pallets = rec.pallets or sum(line.pallets for line in rec.inbound_order_product_ids)

            package_names = []
            if rec.stock_picking_id:
                package_names = rec.stock_picking_id.move_line_ids.mapped("result_package_id.name")
                package_names = [name for name in package_names if name]
            first_package_name = package_names[0] if package_names else ""
            pallet_summary = f"{first_package_name}Etc.{total_pallets}Pallet" if first_package_name else ""
            product_names  = rec.inbound_order_product_ids.inbound_order_product_pallet_ids.mapped('product_id.name')
            product_names = [name for name in product_names if name]
            first_product_name = product_names[0] if product_names else ""
            product_summary = f"{first_product_name},  etc.({total_quantity} pcs)" if first_product_name else ""

            rows.append({
                "inbound_id": rec.id,
                "inbound_no": rec.billno or "",
                "reference": rec.reference or "",
                "bl_no": rec.bl_no or "",
                "container_no": rec.cntr_no or "",
                "inbound_date": portal_format_datetime(rec.i_datetime or rec.a_date or rec.date),
                "portal_inbound_status": state,
                "total_quantity": total_quantity,
                "total_pallets": total_pallets,
                "pallet_summary": pallet_summary,
                "product_summary": product_summary,
            })
        return rows
