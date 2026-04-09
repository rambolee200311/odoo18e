from odoo import api, models, _
from odoo.exceptions import ValidationError


class OutboundOrderBondedUniqueRule(models.Model):
    _inherit = "world.depot.outbound.order"

    def get_is_bonded_outbound_order(self):
        self.ensure_one()
        return self.bonded_flag == "true"

    def action_get_inbound_product_id_set(self, inbound):
        return set(inbound.inbound_order_product_ids.mapped("inbound_order_product_pallet_ids.product_id").ids)

    def action_get_inbound_map_by_unique(self, unique_list, bonded_value):
        inbound_model = self.env["world.depot.inbound.order"]
        unique_list = [x for x in (unique_list or []) if x]
        if not unique_list:
            return {}
        inbound_list = inbound_model.sudo().search([
            ("unique_identifier", "in", unique_list),
            ("is_bonded", "=", bonded_value),
            ("state", "=", "confirm"),
            ("stock_picking_id.state", "=", "done"),
        ], order="id desc")
        result = {}
        for inbound in inbound_list:
            key = (inbound.unique_identifier or "").strip()
            if key and key not in result:
                result[key] = inbound
        return result

    def action_get_ledger_qty_map_by_product_unique(self, product_id_list, unique_list=None):
        self.ensure_one()
        ledger_model = self.env["bonded.identifier.stock.ledger"]
        product_id_list = [x for x in (product_id_list or []) if x]
        if not product_id_list:
            return {}

        domain = [
            ("qty_on_hand", ">", 0),
            ("product_id", "in", product_id_list),
            ("unique_identifier", "!=", False),
        ]
        if unique_list:
            domain.append(("unique_identifier", "in", [x for x in unique_list if x]))
        if self.warehouse and self.warehouse.view_location_id:
            domain.append(("location_id", "child_of", self.warehouse.view_location_id.id))
        if self.mrn_id:
            domain.append(("mrn_id", "=", self.mrn_id.id))

        group_list = ledger_model.sudo().read_group(
            domain,
            ["product_id", "unique_identifier", "qty_on_hand:sum"],
            ["product_id", "unique_identifier"],
            lazy=False,
        )

        qty_map = {}
        for item in group_list:
            product_data = item.get("product_id")
            if not product_data:
                continue
            product_id = product_data[0]
            unique_identifier = (item.get("unique_identifier") or "").strip()
            qty = float(item.get("qty_on_hand") or 0.0)
            if not unique_identifier or qty <= 0:
                continue
            qty_map[(product_id, unique_identifier)] = qty
        return qty_map

    def action_auto_assign_unique_identifier_for_lines(self):
        for rec in self:
            if not rec.get_is_bonded_outbound_order():
                continue
            if not rec.mrn_id:
                raise ValidationError(_("Bonded outbound requires MRN first."))
            if not rec.warehouse or not rec.warehouse.view_location_id:
                raise ValidationError(_("Bonded outbound requires warehouse first."))

            line_list = rec.outbound_order_product_ids.filtered(lambda x: x.product_id and (x.quantity or 0.0) > 0)
            missing_line_list = line_list.filtered(lambda x: not (x.unique_identifier or "").strip())
            if not missing_line_list:
                continue

            product_id_list = list({line.product_id.id for line in missing_line_list})
            qty_map = rec.action_get_ledger_qty_map_by_product_unique(product_id_list)
            unique_list = list({k[1] for k in qty_map.keys()})
            inbound_map = rec.action_get_inbound_map_by_unique(unique_list, bonded_value=True)
            inbound_product_map = {uid: rec.action_get_inbound_product_id_set(inbound) for uid, inbound in inbound_map.items()}

            candidate_map = {}
            for (product_id, unique_identifier), qty in qty_map.items():
                if unique_identifier not in inbound_map:
                    continue
                if product_id not in inbound_product_map.get(unique_identifier, set()):
                    continue
                candidate_map.setdefault(product_id, []).append({"unique_identifier": unique_identifier, "qty_on_hand": qty})

            for product_id, candidate_list in candidate_map.items():
                candidate_list.sort(key=lambda x: x["unique_identifier"])

            for line in missing_line_list:
                candidate_list = candidate_map.get(line.product_id.id, [])
                assigned = False
                for item in candidate_list:
                    if item["qty_on_hand"] + 1e-9 < (line.quantity or 0.0):
                        continue
                    line.write({"unique_identifier": item["unique_identifier"]})
                    item["qty_on_hand"] = item["qty_on_hand"] - (line.quantity or 0.0)
                    assigned = True
                    break
                if not assigned:
                    raise ValidationError(
                        _("No valid bonded stock can satisfy product [%s], qty [%s].")
                        % (line.product_id.display_name, line.quantity or 0.0)
                    )

    def action_validate_outbound_unique_policy(self):
        for rec in self:
            line_list = rec.outbound_order_product_ids.filtered(lambda x: x.product_id and (x.quantity or 0.0) > 0)
            if not line_list:
                continue

            is_bonded = rec.get_is_bonded_outbound_order()

            if is_bonded:
                missing_line_list = line_list.filtered(lambda x: not (x.unique_identifier or "").strip())
                if missing_line_list:
                    raise ValidationError(_("Bonded outbound lines must fill Unique Identifier."))

            use_line_list = line_list.filtered(lambda x: (x.unique_identifier or "").strip())
            if not use_line_list:
                continue

            unique_set = {(line.unique_identifier or "").strip() for line in use_line_list}
            inbound_map = rec.action_get_inbound_map_by_unique(list(unique_set), bonded_value=is_bonded)
            inbound_product_map = {uid: rec.action_get_inbound_product_id_set(inbound) for uid, inbound in inbound_map.items()}

            demand_map = {}
            for line in use_line_list:
                uid = (line.unique_identifier or "").strip()
                inbound = inbound_map.get(uid)
                if not inbound:
                    raise ValidationError(_("Unique Identifier [%s] does not match current bonded policy.") % uid)
                if line.product_id.id not in inbound_product_map.get(uid, set()):
                    raise ValidationError(
                        _("Product [%s] does not belong to inbound of Unique [%s].")
                        % (line.product_id.display_name, uid)
                    )
                key = (line.product_id.id, uid)
                demand_map[key] = demand_map.get(key, 0.0) + (line.quantity or 0.0)

            qty_map = rec.action_get_ledger_qty_map_by_product_unique(
                list({k[0] for k in demand_map.keys()}),
                unique_list=list(unique_set),
            )
            for (product_id, uid), demand_qty in demand_map.items():
                available_qty = float(qty_map.get((product_id, uid)) or 0.0)
                if available_qty + 1e-9 < demand_qty:
                    product = self.env["product.product"].sudo().browse(product_id)
                    raise ValidationError(
                        _("Insufficient stock for product [%s], Unique [%s]. Demand=%s, Available=%s")
                        % (product.display_name, uid, demand_qty, available_qty)
                    )



    @api.onchange("mrn_id", "warehouse", "bonded_flag")
    def onchange_clear_all_line_unique_identifier(self):
        for rec in self:
            if rec.state == "new":
                for line in rec.outbound_order_product_ids:
                    line.unique_identifier = False



    def action_prepare_unique_identifier_before_flow(self):
        for rec in self:
            if rec.get_is_bonded_outbound_order():
                rec.action_auto_assign_unique_identifier_for_lines()
        self.action_validate_outbound_unique_policy()
        return True

    def action_confirm(self):
        self.action_prepare_unique_identifier_before_flow()
        return super().action_confirm()

    def action_create_picking_PICK(self):
        self.action_prepare_unique_identifier_before_flow()
        res = super().action_create_picking_PICK()
        self.actionSyncCustomsDocumentToOutboundPicking()
        return res

    def action_create_picking_PICK_linglong(self):
        raise ValidationError(_("linglong not support."))


    def write(self, vals):
        old_policy_map = {
            rec.id: (
                rec.mrn_id.id if rec.mrn_id else False,
                rec.warehouse.id if rec.warehouse else False,
                rec.bonded_flag or "false",
            )
            for rec in self
        }
        res = super().write(vals)
        for rec in self:
            old_policy = old_policy_map.get(rec.id)
            new_policy = (
                rec.mrn_id.id if rec.mrn_id else False,
                rec.warehouse.id if rec.warehouse else False,
                rec.bonded_flag or "false",
            )
            if rec.state == "new" and old_policy != new_policy:
                rec.action_clear_all_line_unique_identifier()
        return res

    def action_clear_all_line_unique_identifier(self):
        for rec in self:
            if rec.state != "new":
                continue
            rec.write({"outbound_order_product_ids": [(5, 0, 0)]})
