# -*- coding: utf-8 -*-

from odoo import api, models
from odoo.osv import expression

from .utils import (
    portal_apply_date_filters,
    portal_filter_value,
    portal_format_date,
    portal_project_domain,
    portal_product_name,
)


class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    @api.model
    def get_outbound_list(self, filters=None, offset=0, limit=0):
        filters = filters or {}
        domain = portal_project_domain(self.env, "project")
        outbound_no = portal_filter_value(filters, "outbound_no", "reference")
        portal_outbound_status = filters.get("portal_outbound_status")
        container_no = filters.get("container_no")
        bl_no = filters.get("bl_no")
        vsourcebillcode = filters.get("vsourcebillcode")
        cprojectid = filters.get("cprojectid")
        domain.append(("state", "=", "confirm"))
        # if bl_no:
        #     domain.append(("bl_no", "ilike", bl_no))
        # if container_no:
        #     domain.append(("cntr_no", "ilike", container_no))
        if outbound_no:
            domain = expression.AND([domain, ["|", ("billno", "ilike", outbound_no), ("reference", "ilike", outbound_no)]])
        if vsourcebillcode:
            domain = expression.AND([domain, ["|", ("vsourcebillcode", "ilike", vsourcebillcode), ("outbound_order_product_ids.cprojectid", "ilike", vsourcebillcode)]])
        if cprojectid:
            domain.append(("outbound_order_product_ids.cprojectid", "ilike", cprojectid))

        if portal_outbound_status == "outbound_confirmed":
            domain.append(("picking_PICK", "=", False))
        elif portal_outbound_status == "outbound_picking_processing":
            domain += [("picking_PICK", "!=", False), ("picking_PICK.state", "!=", "done")]
        elif portal_outbound_status == "outbound_picking_done":
            domain.append(("picking_PICK.state", "=", "done"))
        portal_apply_date_filters(domain, filters, "picking_PICK_date", ("outbound_date_from",), ("outbound_date_to",))
        outbound_env = self.env["world.depot.outbound.order"].sudo()
        orders = outbound_env.search(domain, order="o_date desc, picking_Out_date desc, date desc, id desc", offset=offset, limit=limit)
        shipping_by_order = self.get_outbound_shipping_map(orders)


        rows = []
        for rec in orders:
            picking = rec.picking_PICK
            if picking and picking.state == "done":
                state = "outbound_picking_done"
            elif picking:
                state = "outbound_picking_processing"
            else:
                state = "outbound_confirmed"
            shipping = shipping_by_order.get(rec.id, {"containers": set(), "bls": set()})
            containers = set(shipping["containers"])
            bls = shipping["bls"]
            if container_no and not any(container_no.lower() in item.lower() for item in containers):
                continue
            if bl_no and not any(bl_no.lower() in item.lower() for item in bls):
                continue
            #total_pallets = sum(line.pallets for line in rec.outbound_order_product_ids)
            total_quantity = sum(line.quantity for line in rec.outbound_order_product_ids)

            # package_names = []
            # if rec.picking_PICK:
            #     package_names = rec.picking_PICK.move_line_ids.mapped("package_id.name")
            #     package_names += rec.picking_PICK.move_line_ids.mapped("result_package_id.name")
            #     package_names = [name for name in package_names if name]
            # first_package_name = package_names[0] if package_names else ""
            # pallet_summary = f"{first_package_name},etc.{total_pallets}Pallet" if first_package_name else ""


            product_names = [portal_product_name(product) for product in rec.outbound_order_product_ids.mapped("product_id") if product]
            contract_no = ", ".join(dict.fromkeys(filter(None, rec.outbound_order_product_ids.mapped("cprojectid"))))

            first_product_name = product_names[0] if product_names else ""
            product_summary = f"{first_product_name},  etc.({total_quantity} pcs)" if first_product_name else ""
            rows.append({
                "outbound_id": rec.id,
                "outbound_no": rec.billno or rec.reference or "",
                "contract_no": contract_no,
                "reference": rec.reference or "",
                "bl_no": ", ".join(sorted(bls)),
                "container_no": ", ".join(sorted(containers)),
                "outbound_date": portal_format_date(rec.picking_PICK_date),
                "portal_outbound_status": state,
                #"total_pallets":total_pallets,
                "total_quantity": total_quantity,
                "picking_no": rec.picking_PICK.name or "",
                #"pallet_summary": pallet_summary,
                "product_summary": product_summary,
            })
        return rows

    @api.model
    @api.model
    def get_outbound_sn_export_rows(self, outbound_id):
        order = self.get_outbound_order(outbound_id)
        if not order:
            return []

        rows = self.get_outbound_detail(outbound_id)

        outbound_date = portal_format_date(
            order.picking_PICK.date_done
            or order.picking_PICK_date
            or order.o_date
            or order.date
        )

        result = []
        for row in rows:
            if not row.get("sn_code"):
                continue

            row.update({
                "project_name": order.project.name or "",
                "type": order.type or "",
                "reference": order.reference or "",
                "outbound_date": outbound_date,
                "picking_no": order.picking_PICK.name or "",
            })
            result.append(row)

        return result



