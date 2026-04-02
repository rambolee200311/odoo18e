from odoo import api, fields, models, _


class BondedIdentifierStockLedger(models.Model):
    _name = "bonded.identifier.stock.ledger"
    _description = "Identifier Stock Ledger"
    _order = "id desc"

    _sql_constraints = [("bucket_key_unique", "unique(bucket_key)", "Bucket Key must be unique.")]

    bucket_key = fields.Char(string="Bucket Key", required=True, index=True, copy=False)
    company_id = fields.Many2one("res.company", string="Company", required=True, index=True, copy=False, default=lambda self: self.env.company)
    product_id = fields.Many2one("product.product", string="Product", required=True, index=True, copy=False)
    location_id = fields.Many2one("stock.location", string="Location", required=True, index=True, copy=False)
    lot_id = fields.Many2one("stock.lot", string="Lot/Serial", index=True, copy=False)
    package_id = fields.Many2one("stock.quant.package", string="Package", index=True, copy=False)
    owner_id = fields.Many2one("res.partner", string="Owner", index=True, copy=False)
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", index=True, copy=False)
    unique_identifier = fields.Char(string="Unique Identifier", index=True, copy=False)
    file_identifier = fields.Char(string="File Identifier", index=True, copy=False)
    qty_on_hand = fields.Float(string="Qty On Hand", copy=False)
    qty_inbound = fields.Float(string="Inbound Qty", copy=False)
    qty_outbound = fields.Float(string="Outbound Qty", copy=False)
    last_move_line_id = fields.Many2one("stock.move.line", string="Last Move Line", index=True, copy=False)
    last_picking_id = fields.Many2one("stock.picking", string="Last Picking", index=True, copy=False)
    last_time = fields.Datetime(string="Last Time", index=True, copy=False)
    remark = fields.Char(string="Remark", copy=False)

    def actionBuildBucketKey(self, vals):
        unique_text = (vals.get("unique_identifier") or "").strip().replace("|", "/")
        file_text = (vals.get("file_identifier") or "").strip().replace("|", "/")
        return "|".join([
            str(vals.get("company_id") or 0),
            str(vals.get("product_id") or 0),
            str(vals.get("location_id") or 0),
            str(vals.get("lot_id") or 0),
            str(vals.get("package_id") or 0),
            str(vals.get("owner_id") or 0),
            str(vals.get("mrn_id") or 0),
            unique_text,
            file_text,
        ])

    def actionGetIdentifierValsByMoveLine(self, move_line):
        unique_identifier = move_line.unique_identifier or move_line.move_id.unique_identifier or move_line.picking_id.unique_identifier or (move_line.lot_id.unique_identifier if move_line.lot_id else False)
        file_identifier = move_line.file_identifier or move_line.picking_id.file_identifier or (move_line.lot_id.file_identifier if move_line.lot_id else False)
        mrn_id = move_line.mrn_id.id or move_line.move_id.mrn_id.id or move_line.picking_id.mrn_id.id or False
        return {"unique_identifier": unique_identifier or False, "file_identifier": file_identifier or False, "mrn_id": mrn_id}

    def actionUpsertLedgerByDelta(self, key_vals, qty_inbound_delta, qty_outbound_delta, move_line):
        bucket_key = self.actionBuildBucketKey(key_vals)
        ledger_ids = self.sudo().search([("bucket_key", "=", bucket_key)], limit=1).ids
        qty_on_hand_delta = (qty_inbound_delta or 0.0) - (qty_outbound_delta or 0.0)

        if ledger_ids:
            ledger = self.browse(ledger_ids[0])
            vals = {
                "qty_on_hand": (ledger.qty_on_hand or 0.0) + qty_on_hand_delta,
                "qty_inbound": (ledger.qty_inbound or 0.0) + (qty_inbound_delta or 0.0),
                "qty_outbound": (ledger.qty_outbound or 0.0) + (qty_outbound_delta or 0.0),
            }
            if not ledger.last_time or move_line.date >= ledger.last_time:
                vals.update({
                    "last_move_line_id": move_line.id,
                    "last_picking_id": move_line.picking_id.id or False,
                    "last_time": move_line.date,
                    "remark": move_line.reference or (move_line.picking_id.origin if move_line.picking_id else False) or False,
                })
            ledger.write(vals)
            return

        create_vals = dict(key_vals)
        create_vals.update({
            "bucket_key": bucket_key,
            "qty_on_hand": qty_on_hand_delta,
            "qty_inbound": qty_inbound_delta or 0.0,
            "qty_outbound": qty_outbound_delta or 0.0,
            "last_move_line_id": move_line.id,
            "last_picking_id": move_line.picking_id.id or False,
            "last_time": move_line.date,
            "remark": move_line.reference or (move_line.picking_id.origin if move_line.picking_id else False) or False,
        })
        self.create(create_vals)

    def actionSyncMoveLineList(self, move_line_list, factor=1.0):
        for move_line in move_line_list:
            if move_line.state != "done" or not move_line.product_id or (move_line.quantity or 0.0) <= 0:
                continue

            id_vals = self.actionGetIdentifierValsByMoveLine(move_line)
            if not id_vals.get("unique_identifier") and not id_vals.get("file_identifier"):
                continue

            common_vals = {
                "company_id": move_line.company_id.id or self.env.company.id,
                "product_id": move_line.product_id.id,
                "lot_id": move_line.lot_id.id or False,
                "owner_id": move_line.owner_id.id or False,
                "mrn_id": id_vals.get("mrn_id") or False,
                "unique_identifier": id_vals.get("unique_identifier") or False,
                "file_identifier": id_vals.get("file_identifier") or False,
            }

            qty = (move_line.quantity or 0.0) * (factor or 1.0)

            if move_line.location_id and move_line.location_id.usage in ("internal", "transit"):
                src_vals = dict(common_vals)
                src_vals.update(
                    {"location_id": move_line.location_id.id, "package_id": move_line.package_id.id or False})
                self.actionUpsertLedgerByDelta(src_vals, 0.0, qty, move_line)

            if move_line.location_dest_id and move_line.location_dest_id.usage in ("internal", "transit"):
                dst_vals = dict(common_vals)
                dst_vals.update({"location_id": move_line.location_dest_id.id,
                                 "package_id": move_line.result_package_id.id or False})
                self.actionUpsertLedgerByDelta(dst_vals, qty, 0.0, move_line)

        return True

