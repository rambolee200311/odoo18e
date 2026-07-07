from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    cmr_sign_time = fields.Datetime(string="CMR Sign Time", tracking=True, copy=False, index=True)
    cmr_sign_file = fields.Binary(string="Signed CMR File", attachment=True)
    cmr_sign_filename = fields.Char(string="CMR Filename")
    unique_identifier = fields.Char(string="Unique Identifier", tracking=True, copy=False, index=True, readonly=True)
    file_identifier = fields.Char(string="File Identifier", tracking=True, copy=False, index=True, readonly=True)
    customs_document_id = fields.Many2one("bonded.customs.document", string="Customs Document", index=True,
                                          tracking=True, copy=False)

    mrn_status = fields.Selection(
        [
            ("pending_declaration", "Pending Declaration"),
            ("declared", "Declared"),
            ("cleared", "Cleared"),
            ("status_changed", "Status Changed"),
            ("exception", "Exception"),
        ],
        string="MRN Status",
        default="pending_declaration",
        tracking=True,
        copy=False,
        index=True,
    )
    bonded_flag = fields.Selection([("true", "bonded"), ("false", "Non-bonded")], string="Bonded Flag",
                                   compute="_compute_bonded_flag", index=True,
                                   readonly=True)

    @api.depends("inbound_order_id", "inbound_order_id.is_bonded",
                 "outbound_order_id",
                 "outbound_order_id.bonded_flag",
                 "mrn_id",
                 "mrn_id.bonded_flag", )
    def _compute_bonded_flag(self):
        for rec in self:
            bonded_value = "false"
            if rec.inbound_order_id:
                bonded_value = "true" if rec.inbound_order_id.is_bonded else "false"
            elif rec.outbound_order_id and rec.outbound_order_id.bonded_flag in ("true", "false"):
                bonded_value = rec.outbound_order_id.bonded_flag

            elif rec.mrn_id and rec.mrn_id.bonded_flag in ("true", "false"):
                bonded_value = rec.mrn_id.bonded_flag

            rec.bonded_flag = bonded_value

    def check_cmr_sign_time_before_done(self):
        for rec in self:
            if rec.picking_type_code != "outgoing":
                continue
            if rec.get_required_is_bonded_by_picking() is not True:
                continue
            if not rec.cmr_sign_time or not rec.cmr_sign_file:
                raise UserError(
                    _("CMR sign time and signed CMR file are required when bonded outbound transfer is Done."))

    @api.constrains("state", "picking_type_id", "cmr_sign_time", "cmr_sign_file", "outbound_order_id", "bonded_flag")
    def check_cmr_sign_time_when_done(self):
        for rec in self:
            if rec.state != "done" or rec.picking_type_code != "outgoing":
                continue
            if rec.get_required_is_bonded_by_picking() is not True:
                continue
            if not rec.cmr_sign_time or not rec.cmr_sign_file:
                raise ValidationError(
                    _("CMR sign time and signed CMR file are required when bonded outbound transfer is Done."))

    def action_sync_identifier_to_move_line_from_picking(self):
        for rec in self:
            if rec.picking_type_code != "incoming":
                continue
            if not rec.unique_identifier and not rec.file_identifier:
                continue
            for line in rec.move_line_ids.filtered(lambda x: x.state != "done"):
                vals = {}
                if rec.unique_identifier and line.unique_identifier != rec.unique_identifier:
                    vals["unique_identifier"] = rec.unique_identifier
                if rec.file_identifier and line.file_identifier != rec.file_identifier:
                    vals["file_identifier"] = rec.file_identifier
                if vals:
                    line.write(vals)
        return True

    def action_check_outgoing_identifier_lines_required(self):
        for rec in self:
            if rec.picking_type_code != "outgoing":
                continue
            required_is_bonded = rec.get_required_is_bonded_by_picking()
            if required_is_bonded is not True:
                continue
            line_list = rec.move_line_ids.filtered(lambda x: (x.quantity or 0.0) > 0)
            missing_line_list = line_list.filtered(lambda x: not x.unique_identifier)
            if missing_line_list:
                raise ValidationError(_("Outbound lines still miss Unique Identifier"))
        return True

    def get_outbound_order_id_from_source_picking(self, vals):
        picking_env = self.env["stock.picking"]
        outbound_env = self.env["world.depot.outbound.order"]

        origin = vals.get("origin")
        if origin:
            origin_picking = picking_env.sudo().search([
                ("name", "=", origin),
                ("outbound_order_id", "!=", False),
            ], limit=1)
            if origin_picking and origin_picking.outbound_order_id.is_bonded is True:
                return origin_picking.outbound_order_id.id

            outbound = outbound_env.sudo().search([
                ("billno", "=", origin),
                ("is_bonded", "=", True),
            ], limit=1)
            if outbound:
                return outbound.id

        group_id = vals.get("group_id")
        if group_id:
            group_picking = picking_env.sudo().search([
                ("group_id", "=", group_id),
                ("outbound_order_id", "!=", False),
            ], order="id asc", limit=1)
            if group_picking and group_picking.outbound_order_id.is_bonded is True:
                return group_picking.outbound_order_id.id

        return False

    @api.model_create_multi
    def create(self, vals_list):
        inbound_env = self.env["world.depot.inbound.order"]
        picking_env = self.env["stock.picking"]
        for vals in vals_list:
            if not vals.get("outbound_order_id"):
                outbound_order_id = self.get_outbound_order_id_from_source_picking(vals)
                if outbound_order_id:
                    vals["outbound_order_id"] = outbound_order_id
            if not vals.get("unique_identifier") and vals.get("inbound_order_id"):
                inbound = inbound_env.sudo().browse(vals["inbound_order_id"])
                vals["unique_identifier"] = inbound.unique_identifier or vals.get("unique_identifier")
                if not vals.get("file_identifier"):
                    vals["file_identifier"] = inbound.file_identifier or vals.get("file_identifier")
            if not vals.get("unique_identifier") and vals.get("origin"):
                origin_picking = picking_env.sudo().search([("name", "=", vals["origin"])], limit=1)
                if origin_picking:
                    vals["unique_identifier"] = origin_picking.unique_identifier or vals.get("unique_identifier")
                    if not vals.get("file_identifier"):
                        vals["file_identifier"] = origin_picking.file_identifier or vals.get("file_identifier")
        records = super().create(vals_list)
        records.action_sync_identifier_to_move_line_from_picking()
        return records

    def write(self, vals):
        if self.env.context.get("skip_identifier_sync"):
            return super().write(vals)

        vals_write = dict(vals)
        if not vals_write.get("unique_identifier") and vals_write.get("inbound_order_id"):
            inbound = self.env["world.depot.inbound.order"].sudo().browse(vals_write["inbound_order_id"])
            vals_write["unique_identifier"] = inbound.unique_identifier or vals_write.get("unique_identifier")
            if not vals_write.get("file_identifier"):
                vals_write["file_identifier"] = inbound.file_identifier or vals_write.get("file_identifier")
        if not vals_write.get("unique_identifier") and vals_write.get("origin"):
            origin_picking = self.env["stock.picking"].sudo().search([("name", "=", vals_write["origin"])], limit=1)
            if origin_picking:
                vals_write["unique_identifier"] = origin_picking.unique_identifier or vals_write.get(
                    "unique_identifier")
                if not vals_write.get("file_identifier"):
                    vals_write["file_identifier"] = origin_picking.file_identifier or vals_write.get("file_identifier")

        res = super().write(vals_write)
        self.action_sync_identifier_to_move_line_from_picking()
        return res

    def actionPostLedgerByPicking(self):
        ledger_model = self.env["bonded.identifier.stock.ledger"]
        for rec in self:
            if rec.picking_type_code not in ("incoming", "outgoing", "internal"):
                continue
            line_list = rec.move_line_ids.filtered(
                lambda x: x.state == "done" and (x.quantity or 0.0) > 0 and not x.ledger_posted)
            if line_list:
                ledger_model.actionSyncMoveLineList(line_list, factor=1.0)
                line_list.write({"ledger_posted": True})
        return True

    def actionReverseLedgerByPicking(self):
        ledger_model = self.env["bonded.identifier.stock.ledger"]
        for rec in self:
            line_list = rec.move_line_ids.filtered(lambda x: x.ledger_posted and (x.quantity or 0.0) > 0)
            if line_list:
                ledger_model.actionSyncMoveLineList(line_list, factor=-1.0)
                line_list.write({"ledger_posted": False})
        return True

    def action_cancel(self):
        res = super().action_cancel()
        self.actionReverseLedgerByPicking()
        return res

    def get_move_line_done_qty(self, line):
        if "quantity" in line._fields:
            return line.quantity or 0.0
        if "qty_done" in line._fields:
            return line.qty_done or 0.0
        return 0.0

    def get_required_is_bonded_by_picking(self):
        self.ensure_one()
        if self.picking_type_code == "incoming" and self.inbound_order_id:
            return bool(self.inbound_order_id.is_bonded)

        if self.picking_type_code == "outgoing":
            if self.outbound_order_id and self.outbound_order_id.bonded_flag in ("true", "false"):
                return self.outbound_order_id.bonded_flag == "true"
            if self.bonded_flag in ("true", "false"):
                return self.bonded_flag == "true"

        return None

    def check_location_bonded_policy(self):
        for rec in self:
            required_is_bonded = rec.get_required_is_bonded_by_picking()
            if required_is_bonded is None:
                continue

            line_list = rec.move_line_ids.filtered(lambda x: rec.get_move_line_done_qty(x) > 0)

            if rec.picking_type_code == "incoming":
                location_list = line_list.mapped("location_dest_id").filtered(
                    lambda x: x.usage in ("internal", "transit"))
                wrong_location_list = location_list.filtered(lambda x: bool(x.is_bonded) != required_is_bonded)
                if wrong_location_list:
                    location_text = ", ".join(wrong_location_list.mapped("complete_name")[:5])
                    raise ValidationError(
                        _(
                            "Inbound location bonded policy mismatch. Required bonded=%(required)s, wrong destination locations: %(locations)s"
                        ) % {
                            "required": "true" if required_is_bonded else "false",
                            "locations": location_text,
                        }
                    )

            if rec.picking_type_code == "outgoing":
                location_list = line_list.mapped("location_id").filtered(lambda x: x.usage in ("internal", "transit"))
                wrong_location_list = location_list.filtered(lambda x: bool(x.is_bonded) != required_is_bonded)
                if wrong_location_list:
                    location_text = ", ".join(wrong_location_list.mapped("complete_name")[:5])
                    raise ValidationError(
                        _(
                            "Outbound source location bonded policy mismatch. Required bonded=%(required)s, wrong source locations: %(locations)s"
                        ) % {
                            "required": "true" if required_is_bonded else "false",
                            "locations": location_text,
                        }
                    )

    def button_validate(self):
        # 验证保税入库只能入保税库位,出库同
        self.check_location_bonded_policy()

        outgoing_pickings = self.filtered(lambda x: x.picking_type_code == "outgoing")
        outgoing_pickings.action_check_outgoing_identifier_lines_required()

        for rec in self:
            rec.check_cmr_sign_time_before_done()


        res = super().button_validate()

        done_pickings = self.filtered(lambda x: x.state == "done")
        if done_pickings:
            done_pickings.actionPostLedgerByPicking()

            for rec in done_pickings:
                if rec.outbound_order_id and rec.cmr_sign_time:
                    rec.outbound_order_id.write({"cmr_sign_time": rec.cmr_sign_time})

        return res


class StockLot(models.Model):
    _inherit = "stock.lot"

    unique_identifier = fields.Char(string="Unique Identifier", copy=False, index=True)
    file_identifier = fields.Char(string="File Identifier", copy=False, index=True)
