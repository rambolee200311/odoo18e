from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


def get_reference_vals(product):
    return {
        "origin_country": product.origin_country.id or False,
        "goods_value": product.goods_value or 0.0,
        "hs_code": product.hs_code or False,
        "weight": product.weight or 0.0,
        "customs_code": product.customs_code or False,
    }


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    origin_country = fields.Many2one("res.country", string="Country of Origin", tracking=True, index=True)
    goods_value = fields.Monetary(
        string='Goods Value',
        currency_field='currency_id',
        tracking=True)
    hs_code = fields.Char(string="HS Code", tracking=True, readonly=True, index=True)
    weight = fields.Float(string="Weight", tracking=True)
    customs_code = fields.Char(string="Customs Code", tracking=True, readonly=True, index=True)

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id)

    unique_identifier = fields.Char(string='Unique Identifier', related='move_id.unique_identifier', store=True,
                                    readonly=True, index=True)
    file_identifier = fields.Char(string='File Identifier', tracking=True, copy=False, index=True)

    io_picking_id = fields.Many2one("stock.picking", string="IO", compute="_compute_io_oo_picking_id", store=True,
                                    readonly=True, index=True)
    oo_picking_id = fields.Many2one("stock.picking", string="OO", compute="_compute_io_oo_picking_id", store=True,
                                    readonly=True, index=True)
    in_no = fields.Char(string="IN No", related="io_picking_id.name", store=True, readonly=True, index=True)
    pick_no = fields.Char(string="PICK No", related="picking_id.name", store=True, readonly=True, index=True)

    mrn_code = fields.Char(string="MRN Code", tracking=True, copy=False, index=True)
    mrn_status = fields.Selection([
        ("pending_declaration", "Pending Declaration"),
        ("declared", "Declared"),
        ("cleared", "Cleared"),
        ("status_changed", "Status Changed"),
        ("exception", "Exception"),
    ], string="MRN Status", default="pending_declaration", tracking=True, copy=False, index=True)

    @api.depends(
        "picking_id",
        "picking_id.picking_type_id.code",
        "picking_id.inbound_order_id",
        "picking_id.inbound_order_id.stock_picking_id",
        "picking_id.outbound_order_id",
        "picking_id.outbound_order_id.picking_PICK",
        "picking_id.outbound_order_id.picking_Out",
        "unique_identifier",
    )
    def _compute_io_oo_picking_id(self):
        picking_model = self.env["stock.picking"]
        identifier_list = list({rec.unique_identifier for rec in self if rec.unique_identifier})
        io_map = {}
        oo_map = {}

        if identifier_list:
            io_pickings = picking_model.sudo().search(
                [("unique_identifier", "in", identifier_list), ("picking_type_id.code", "=", "incoming"),
                 ("state", "!=", "cancel")],
                order="date_done desc,id desc",
            )
            oo_pickings = picking_model.sudo().search(
                [("unique_identifier", "in", identifier_list), ("picking_type_id.code", "=", "outgoing"),
                 ("state", "!=", "cancel")],
                order="date_done desc,id desc",
            )
            for picking in io_pickings:
                io_map.setdefault(picking.unique_identifier, picking.id)
            for picking in oo_pickings:
                oo_map.setdefault(picking.unique_identifier, picking.id)

        for rec in self:
            io_id = False
            oo_id = False
            picking_code = rec.picking_id.picking_type_id.code if rec.picking_id and rec.picking_id.picking_type_id else False

            if picking_code == "incoming":
                io_id = rec.picking_id.id
            elif rec.picking_id.inbound_order_id and rec.picking_id.inbound_order_id.stock_picking_id:
                io_id = rec.picking_id.inbound_order_id.stock_picking_id.id
            elif rec.unique_identifier and io_map.get(rec.unique_identifier):
                io_id = io_map[rec.unique_identifier]

            if picking_code == "outgoing":
                oo_id = rec.picking_id.id
            elif rec.picking_id.outbound_order_id:
                oo_picking = rec.picking_id.outbound_order_id.picking_Out or rec.picking_id.outbound_order_id.picking_PICK
                oo_id = oo_picking.id if oo_picking else False
            elif rec.unique_identifier and oo_map.get(rec.unique_identifier):
                oo_id = oo_map[rec.unique_identifier]

            rec.io_picking_id = io_id
            rec.oo_picking_id = oo_id


    @api.onchange("product_id", "move_id")
    def onchange_product_id_fill_reference_fields(self):
        for rec in self:
            product = rec.product_id or rec.move_id.product_id
            if product:
                vals = get_reference_vals(product)
                rec.origin_country = vals["origin_country"]
                rec.goods_value = vals["goods_value"]
                rec.hs_code = vals["hs_code"]
                rec.weight = vals["weight"]
                rec.customs_code = vals["customs_code"]

    @api.model_create_multi
    def create(self, vals_list):
        move_model = self.env["stock.move"]
        picking_model = self.env["stock.picking"]
        for vals in vals_list:
            if not vals.get("file_identifier"):
                picking = False
                if vals.get("picking_id"):
                    picking = picking_model.sudo().browse(vals["picking_id"])
                elif vals.get("move_id"):
                    picking = move_model.sudo().browse(vals["move_id"]).picking_id
                if picking and picking.file_identifier:
                    vals["file_identifier"] = picking.file_identifier

        product_env = self.env["product.product"].sudo()
        move_env = self.env["stock.move"].sudo()
        for vals in vals_list:
            product_id = vals.get("product_id")
            if not product_id and vals.get("move_id"):
                product_id = move_env.browse(vals["move_id"]).product_id.id
            if not product_id:
                continue
            vals_ref = get_reference_vals(product_env.browse(product_id))
            vals.setdefault("origin_country", vals_ref["origin_country"])
            vals.setdefault("goods_value", vals_ref["goods_value"])
            vals.setdefault("weight", vals_ref["weight"])
            vals["hs_code"] = vals_ref["hs_code"]
            vals["customs_code"] = vals_ref["customs_code"]
        return super().create(vals_list)

    def write(self, vals):

        protected_field_set = {"unique_identifier", "file_identifier", "io_picking_id", "oo_picking_id", "in_no",
                               "pick_no"}
        if protected_field_set.intersection(vals):
            for rec in self:
                if rec.state == "done":
                    raise UserError(
                        _("Done stock move lines keep full history and cannot overwrite identifier fields."))

        vals_write = dict(vals)
        if "file_identifier" not in vals_write:
            if vals_write.get("picking_id"):
                picking = self.env["stock.picking"].sudo().browse(vals_write["picking_id"])
                if picking and picking.file_identifier:
                    vals_write["file_identifier"] = picking.file_identifier
            elif vals_write.get("move_id"):
                move = self.env["stock.move"].sudo().browse(vals_write["move_id"])
                if move and move.picking_id and move.picking_id.file_identifier:
                    vals_write["file_identifier"] = move.picking_id.file_identifier


        #产品
        if ("hs_code" in vals or "customs_code" in vals) and "product_id" not in vals and "move_id" not in vals:
            raise UserError(_("HS Code and Customs Code are reference values and cannot be modified."))
        if vals.get("product_id") or vals.get("move_id"):
            product_env = self.env["product.product"].sudo()
            move_env = self.env["stock.move"].sudo()
            product_id = vals.get("product_id")
            if not product_id and vals.get("move_id"):
                product_id = move_env.browse(vals["move_id"]).product_id.id
            if product_id:
                vals_ref = get_reference_vals(product_env.browse(product_id))
                vals = dict(vals)
                vals["hs_code"] = vals_ref["hs_code"]
                vals["customs_code"] = vals_ref["customs_code"]
                vals.setdefault("origin_country", vals_ref["origin_country"])
                vals.setdefault("goods_value", vals_ref["goods_value"])
                vals.setdefault("weight", vals_ref["weight"])
        return super().write(vals)



    @api.constrains("io_picking_id", "oo_picking_id")
    def check_io_oo_picking_type(self):
        for rec in self:
            if rec.io_picking_id and rec.io_picking_id.picking_type_id.code != "incoming":
                raise ValidationError(_("IO must be an incoming picking."))
            # if rec.oo_picking_id and rec.oo_picking_id.picking_type_id.code != "outgoing":
            #     raise ValidationError(_("OO must be an outgoing picking."))


    @api.constrains("state", "unique_identifier", "file_identifier")
    def check_identifier_required_when_done(self):
        for rec in self:
            if rec.state == "done" and (not rec.unique_identifier or not rec.file_identifier):
                raise ValidationError(_("Unique Identifier and File Identifier are required when stock move line is Done."))

    def unlink(self):
        for rec in self:
            if rec.state == "done":
                raise UserError(_("Done stock move lines are history records and cannot be deleted."))
        return super().unlink()