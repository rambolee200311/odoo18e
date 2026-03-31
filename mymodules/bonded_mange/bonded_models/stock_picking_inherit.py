from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    cmr_sign_time = fields.Datetime(string="CMR Sign Time", tracking=True, copy=False, index=True)
    cmr_sign_file = fields.Binary(string="Signed CMR File", attachment=True, tracking=True)
    cmr_sign_filename = fields.Char(string="CMR Filename")
    unique_identifier = fields.Char(string="Unique Identifier", tracking=True, copy=False, index=True, readonly=True)
    file_identifier = fields.Char(string="File Identifier", tracking=True, copy=False, index=True, readonly=True)

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

    def check_cmr_sign_time_before_done(self):
        for rec in self:
            if rec.picking_type_code in ("outgoing",) and (not rec.cmr_sign_time or not rec.cmr_sign_file):
                raise UserError(_("CMR sign time and signed CMR file are required when transfer is Done (outgoing)."))

    @api.constrains("state", "picking_type_id", "cmr_sign_time")
    def check_cmr_sign_time_when_done(self):
        for rec in self:
            if rec.state == "done" and rec.picking_type_code in ("outgoing",) and not rec.cmr_sign_time and not rec.cmr_sign_file:
                raise ValidationError(_("CMR sign time and signed CMR file are required when transfer is Done (outgoing)."))

    def actionSyncIdentifierToMoveLineFromPicking(self):
        for rec in self:
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

    def actionBackfillOutgoingIdentifierFromLedger(self):
        for rec in self:
            if rec.picking_type_code != "outgoing":
                continue

            line_list = rec.move_line_ids.filtered(lambda x: (x.quantity or 0.0) > 0)
            line_list.actionFillIdentifierForOutgoingByLedger(raise_if_missing=True)

            pair_set = {
                (line.unique_identifier or False, line.file_identifier or False)
                for line in line_list
                if line.unique_identifier or line.file_identifier
            }
            if not pair_set:
                raise ValidationError(_("Outbound picking lines miss Unique Identifier or File Identifier."))
            if len(pair_set) > 1:
                raise ValidationError(_("Outbound picking contains multiple identifier pairs. Please split by identifier pair."))
            #回写picking出库
            unique_identifier, file_identifier = list(pair_set)[0]
            vals = {}
            if unique_identifier and rec.unique_identifier != unique_identifier:
                vals["unique_identifier"] = unique_identifier
            if file_identifier and rec.file_identifier != file_identifier:
                vals["file_identifier"] = file_identifier
            if vals:
                rec.with_context(skip_identifier_sync=True).write(vals)

            rec.actionSyncIdentifierToMoveLineFromPicking()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        inbound_env = self.env["world.depot.inbound.order"]
        picking_env = self.env["stock.picking"]
        for vals in vals_list:
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
        records.actionSyncIdentifierToMoveLineFromPicking()
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
                vals_write["unique_identifier"] = origin_picking.unique_identifier or vals_write.get("unique_identifier")
                if not vals_write.get("file_identifier"):
                    vals_write["file_identifier"] = origin_picking.file_identifier or vals_write.get("file_identifier")

        res = super().write(vals_write)
        self.actionSyncIdentifierToMoveLineFromPicking()
        return res

    def button_validate(self):
        outgoing_pickings = self.filtered(lambda x: x.picking_type_code == "outgoing")
        for rec in outgoing_pickings:
            rec.actionBackfillOutgoingIdentifierFromLedger()

        for rec in self:
            rec.check_cmr_sign_time_before_done()

        res = super().button_validate()

        done_pickings = self.filtered(lambda x: x.state == "done")
        if done_pickings:
            done_pickings.action_sync_identifier_to_stock_flow()
            ledger_model = self.env["bonded.identifier.stock.ledger"]
            for rec in done_pickings.filtered(lambda x: x.picking_type_code in ("incoming", "outgoing", "internal")):
                move_lines = rec.move_line_ids.filtered(lambda x: x.state == "done" and (x.quantity or 0.0) > 0)
                ledger_model.actionSyncMoveLineList(move_lines)

            for rec in done_pickings:
                if rec.outbound_order_id and rec.cmr_sign_time:
                    rec.outbound_order_id.write({"cmr_sign_time": rec.cmr_sign_time})

        return res

    def action_sync_identifier_to_stock_flow(self):
        quant_env = self.env["stock.quant"]
        for rec in self:
            if not rec.unique_identifier and not rec.file_identifier:
                continue
            for lot in rec.move_line_ids.mapped("lot_id").filtered(lambda x: x):
                vals = {}
                if rec.unique_identifier and not lot.unique_identifier:
                    vals["unique_identifier"] = rec.unique_identifier
                if rec.file_identifier and not lot.file_identifier:
                    vals["file_identifier"] = rec.file_identifier
                if vals:
                    lot.write(vals)

            for move_line in rec.move_line_ids.filtered(lambda x: x.location_dest_id.usage in ("internal", "transit") and x.quantity):
                domain = [
                    ("product_id", "=", move_line.product_id.id),
                    ("location_id", "=", move_line.location_dest_id.id),
                    ("lot_id", "=", move_line.lot_id.id or False),
                    ("package_id", "=", move_line.result_package_id.id or False),
                    ("owner_id", "=", move_line.owner_id.id or False),
                ]
                quant_ids = quant_env.sudo().search(domain).ids
                for quant in quant_env.browse(quant_ids):
                    vals = {}
                    if rec.unique_identifier and not quant.unique_identifier:
                        vals["unique_identifier"] = rec.unique_identifier
                    if rec.file_identifier and not quant.file_identifier:
                        vals["file_identifier"] = rec.file_identifier
                    if vals:
                        quant.write(vals)
        return True


class StockLot(models.Model):
    _inherit = "stock.lot"

    unique_identifier = fields.Char(string="Unique Identifier", copy=False, index=True)
    file_identifier = fields.Char(string="File Identifier", copy=False, index=True)
