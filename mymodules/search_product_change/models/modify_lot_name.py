from odoo import api, fields, models, _


class ModifyLotName(models.Model):
    _name = "modify.lot.name"
    _description = "Modify Lot Name"
    _order = "id desc"
    _rec_name = 'reference'

    picking_id = fields.Many2one("stock.picking", string="Pick", required=True, domain=[("picking_type_id.code", "=", "internal")], index=True, copy=False)
    reference = fields.Char(string="Order Reference", compute="compute_reference", store=True, readonly=True, copy=False, index=True)
    change_type = fields.Selection([("normal", "Normal Modify"), ("exchange", "SN Exchange")], string="Change Type",
                                   default="normal", required=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", string="Project", compute="compute_project_id", store=True, readonly=True, copy=False, index=True)
    reason = fields.Text(string="Reason", required=True, copy=False)
    policy = fields.Text(string="Policy", default="""1. Record status must be Draft. If it is Confirmed, operation is not allowed.
    2. Old SN and New SN are required.
    3. Old SN and New SN cannot be the same.
    4. Product must be serial-tracked, tracking='serial'. Otherwise, show: Product is not serial-tracked.
    5. Old SN must exist in stock.move.line.lot_id.name of the current picking. Otherwise, show: Old SN is not in the picking details.
    6. If Old SN matches multiple different lot_id records in picking lines, the user must check manually.
    7. New SN must not duplicate an existing stock.lot.name under the same product. Otherwise, show: New SN already exists.
    8. If the lot_id of Old SN has been used in another completed picking, this record cannot be modified. Error Message: Old SN has been used in picking [XXX]. Please fix the historical picking first.""",
                         readonly=True, copy=False)
    error_message = fields.Text(string="Error Message", readonly=True, copy=False)
    state = fields.Selection([("draft", "Draft"), ("confirmed", "Confirmed"), ("rollback", "Rollback")], string="State", default="draft", required=True, index=True, copy=False)
    changed_by_id = fields.Many2one("res.users", string="Changed By", readonly=True, copy=False)
    change_date = fields.Datetime(string="Change Date", readonly=True, copy=False)
    rollback_by_id = fields.Many2one("res.users", string="Rollback By", readonly=True, copy=False)
    rollback_date = fields.Datetime(string="Rollback Date", readonly=True, copy=False)
    sn_change_lines = fields.One2many("modify.lot.name.line", "modify_lot_name_id", string="SN List", copy=False)
    allowed_product_line_ids = fields.Many2many("product.product", string="Allowed Products",
                                                compute="compute_allowed_product_line_ids")

    @api.depends("picking_id", "picking_id.move_line_ids.product_id")
    def compute_allowed_product_line_ids(self):
        move_line_env = self.env["stock.move.line"].sudo()
        for rec in self:
            products = self.env["product.product"]
            if rec.picking_id:
                move_lines = move_line_env.search(
                    [("picking_id", "=", rec.picking_id.id), ("product_id.tracking", "=", "serial")])
                products = move_lines.mapped("product_id")
            rec.allowed_product_line_ids = products

    @api.depends("picking_id", "picking_id.ref_1")
    def compute_reference(self):
        for rec in self:
            rec.reference = rec.picking_id.ref_1 or rec.picking_id.outbound_order_id.reference

    @api.depends("picking_id", "picking_id.outbound_order_id.project")
    def compute_project_id(self):
        for rec in self:
            project = rec.env["project.project"]
            if rec.picking_id.outbound_order_id and rec.picking_id.outbound_order_id.project:
                project = rec.picking_id.outbound_order_id.project
            elif rec.picking_id and "project_id" in rec.picking_id._fields:
                project = rec.picking_id.project_id
            rec.project_id = project

    def action_confirm_modify(self):
        for rec in self:
            main_errors = []
            line_errors = []
            line_results = []

            rec.sn_change_lines.write({"error_message": False})
            rec.write({"error_message": False})

            if rec.state != "draft":
                main_errors.append(_("Only draft records can be confirmed."))
            if not rec.picking_id:
                main_errors.append(_("Pick is required."))
            elif rec.picking_id.picking_type_id.code != "internal":
                main_errors.append(_("Only internal picking can be modified."))
            elif rec.picking_id.state in ("cancel",):
                main_errors.append(_("Cancelled picking cannot be modified."))
            if not rec.reason:
                main_errors.append(_("Reason is required."))
            if not rec.sn_change_lines:
                main_errors.append(_("SN List is required."))

            if rec.change_type == "exchange" and len(rec.sn_change_lines) < 2:
                main_errors.append(_("SN Exchange requires at least two lines."))

            if main_errors:
                message = "\n".join(main_errors)
                rec.write({"error_message": message})
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {"title": _("Modify Lot Name"), "message": message, "type": "danger", "sticky": True},
                }

            move_line_env = rec.env["stock.move.line"].sudo()
            lot_env = rec.env["stock.lot"].sudo()

            for line in rec.sn_change_lines:
                errors = []

                old_name = (line.old_name or "").strip()
                new_name = (line.new_name or "").strip()
                if not line.product_id:
                    errors.append(_("Product is required."))
                elif line.product_id.tracking != "serial":
                    errors.append(_("Product is not serial-tracked."))
                if not old_name or not new_name:
                    errors.append(_("Old SN and New SN are required."))
                elif old_name == new_name:
                    errors.append(_("Old SN and New SN are the same."))

                lot = rec.env["stock.lot"]
                move_line = rec.env["stock.move.line"]
                if not errors:
                    move_lines = move_line_env.search([
                        ("picking_id", "=", rec.picking_id.id),
                        ("product_id", "=", line.product_id.id),
                        ("lot_id.name", "=", old_name),
                        ("lot_id", "!=", False),
                    ])
                    lots = move_lines.mapped("lot_id")
                    if len(lots) > 1:
                        errors.append(_("Old SN matched multiple lots in this pick. Please check manually."))
                    elif lots:
                        lot = rec.env["stock.lot"].browse(lots.id)
                        move_line = rec.env["stock.move.line"].browse(move_lines[:1].id)
                    else:
                        errors.append(_("Old SN is not in the picking details."))

                if not errors and lot.product_id.tracking != "serial":
                    errors.append(_("Product is not serial-tracked."))

                if not errors:
                    used_line = move_line_env.search([
                        ("lot_id", "=", lot.id),
                        ("product_id", "=", line.product_id.id),
                        ("picking_id", "!=", rec.picking_id.id),
                        ("picking_id.state", "=", "done"),
                        ("picking_id.picking_type_id.code", "in", ["incoming", "internal", "outgoing"]),
                    ], limit=1)
                    if used_line:
                        errors.append(_("Old SN has been used in picking [%s]. Please fix the historical picking first.") % (used_line.picking_id.name or used_line.picking_id.display_name))

                if errors:
                    message = "\n".join(errors)
                    line.write({"error_message": message})
                    line_errors.append(message)
                else:
                    line_results.append((line, lot, move_line, new_name))

            if line_errors:
                message = "\n".join(line_errors)
                rec.write({"error_message": message})
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {"title": _("Modify Lot Name"), "message": message, "type": "danger", "sticky": True},
                }

            seen_new_names = set()
            seen_lot_ids = set()
            for line, lot, move_line, new_name in line_results:
                new_key = new_name
                if new_key in seen_new_names:
                    line_errors.append(_("Duplicate New SN in this modify record: %s.") % new_name)
                seen_new_names.add(new_key)
                if lot.id in seen_lot_ids:
                    line_errors.append(_("The same lot is selected by multiple lines: %s.") % (lot.display_name,))
                seen_lot_ids.add(lot.id)


            target_lot_ids = set()
            for line, lot, move_line, new_name in line_results:
                target_lot_ids.add(lot.id)

            for line, lot, move_line, new_name in line_results:
                existing_lots = lot_env.search([("name", "=", new_name), ("id", "!=", lot.id)])
                if rec.change_type == "normal":
                    if existing_lots:
                        line_errors.append(_("New SN already exists: %s.") % new_name)
                else:
                    outside_lots = existing_lots.filtered(lambda existing_lot: existing_lot.id not in target_lot_ids)
                    if outside_lots:
                        line_errors.append(
                            _("New SN is occupied by another lot outside this modify record: %s.") % new_name)
            if line_errors:
                message = "\n".join(line_errors)
                rec.write({"error_message": message})
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {"title": _("Modify Lot Name"), "message": message, "type": "danger", "sticky": True},
                }

            if rec.change_type == "exchange":
                for line, lot, move_line, new_name in line_results:
                    temp_name = "__tmp_modify_lot_name_%s_%s" % (rec.id, lot.id)
                    rec.env["stock.lot"].browse(lot.id).write({"name": temp_name})

            for line, lot, move_line, new_name in line_results:
                line.write({
                    "lot_id": lot.id,
                    "move_line_id": move_line.id or False,
                    "old_name": (line.old_name or "").strip(),
                    "new_name": new_name,
                    "error_message": False,
                })
                rec.env["stock.lot"].browse(lot.id).write({"name": new_name})

            rec.write({"state": "confirmed", "changed_by_id": rec.env.user.id, "change_date": fields.Datetime.now(), "error_message": False})
        return True

    def action_rollback_modify(self):
        for rec in self:
            errors = []
            line_results = []

            rec.sn_change_lines.write({"error_message": False})
            rec.write({"error_message": False})

            if rec.state != "confirmed":
                errors.append(_("Only confirmed records can be rolled back."))
            if not rec.sn_change_lines:
                errors.append(_("SN List is required."))

            lot_env = rec.env["stock.lot"].sudo()

            for line in rec.sn_change_lines:
                old_name = (line.old_name or "").strip()
                new_name = (line.new_name or "").strip()
                if not line.lot_id:
                    errors.append(_("Line %s has no matched lot.") % (line.display_name,))
                    continue
                if line.lot_id.name != new_name:
                    errors.append(_("Current lot name is not New SN for %s.") % new_name)
                    continue
                line_results.append((line, line.lot_id, old_name))

            target_lot_ids = set()
            for line, lot, old_name in line_results:
                target_lot_ids.add(lot.id)

            for line, lot, old_name in line_results:
                existing_lots = lot_env.search([("name", "=", old_name), ("id", "!=", lot.id)])

                if rec.change_type == "normal":
                    if existing_lots:
                        errors.append(_("Old SN already exists: %s.") % old_name)
                else:
                    outside_lots = existing_lots.filtered(lambda existing_lot: existing_lot.id not in target_lot_ids)
                    if outside_lots:
                        errors.append(_("Old SN is occupied by another lot outside this modify record: %s.") % old_name)

            if errors:
                message = "\n".join(errors)
                rec.write({"error_message": message})
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {"title": _("Modify Lot Name"), "message": message, "type": "danger", "sticky": True},
                }

            if rec.change_type == "exchange":
                for line, lot, old_name in line_results:
                    temp_name = "__tmp_rollback_lot_name_%s_%s" % (rec.id, lot.id)
                    lot.write({"name": temp_name})

            for line, lot, old_name in line_results:
                lot.write({"name": old_name})

            rec.write({"state": "rollback", "rollback_by_id": rec.env.user.id, "rollback_date": fields.Datetime.now(),
                       "error_message": False})
        return True


class ModifyLotNameLine(models.Model):
    _name = "modify.lot.name.line"
    _description = "Modify Lot Name Line"
    _order = "id desc"

    modify_lot_name_id = fields.Many2one("modify.lot.name", string="Modify Lot Name", required=True, ondelete="cascade", index=True)
    product_id = fields.Many2one("product.product", string="Product", required=True, domain=[("tracking", "=", "serial")], index=True, copy=False)
    old_name = fields.Char(string="Old SN", required=True, index=True, copy=False)
    new_name = fields.Char(string="New SN", required=True, index=True, copy=False)
    lot_id = fields.Many2one("stock.lot", string="Lot", readonly=True, index=True, copy=False)
    move_line_id = fields.Many2one("stock.move.line", string="Move Line", readonly=True, index=True, copy=False)
    error_message = fields.Text(string="Error Message", readonly=True, copy=False)
