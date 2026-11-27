from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    outbound_scan_mode = fields.Selection([('whole_pallet', 'Whole Pallet'), ('partial_pallet', 'Partial Pallet')], string='Outbound Scan Mode', copy=False, index=True)
    is_unspecified_pallet_outgoing = fields.Boolean(string='Unspecified Pallet Outgoing', copy=False, index=True)
    project_pallet_structure_mode = fields.Selection(related='project_id.pallet_structure_mode', string='Pallet Structure Mode', readonly=True)
    outbound_preparation_state = fields.Selection([('not_required', 'Not Required'), ('prepared', 'Prepared')], string='Outbound Preparation Status',tracking=True, required=True, default='not_required', readonly=True, copy=False, index=True)
    outbound_prepared_by_id = fields.Many2one('res.users', string='Outbound Prepared By', readonly=True, copy=False, tracking=True,ondelete='restrict')
    outbound_prepared_at = fields.Datetime(string='Outbound Prepared At', readonly=True,tracking=True, copy=False)

    def action_validate_secondary_outbound(self):
        for rec in self:
            if rec.picking_type_code != 'outgoing' or rec.state in ('done', 'cancel'):
                raise UserError(_('Only pending outgoing pickings can be confirmed for secondary outbound.'))
        self.with_context(skip_secondary_outbound_validation=True, skip_backorder=True).button_validate()
        if any(rec.state != 'done' for rec in self):
            raise UserError(_('Secondary outbound confirmation could not complete all outgoing pickings.'))
        return True

    def clear_incomplete_whole_pallet_result_packages(self):
        move_line_model = self.env["stock.move.line"]
        quant_model = self.env["stock.quant"]
        for rec in self:
            if not rec.is_unspecified_pallet_outgoing or rec.state in ("done", "cancel"):
                continue
            whole_lines = move_line_model.sudo().search([("picking_id", "=", rec.id), ("state", "not in", ("done", "cancel")), ("package_id", "!=", False), ("result_package_id", "!=", False), ("quantity", ">", 0)])
            whole_packages = whole_lines.filtered(lambda line: line.package_id == line.result_package_id).mapped("package_id")
            for package in whole_packages:
                scanned_lines = move_line_model.sudo().search([("picking_id", "=", rec.id), ("state", "not in", ("done", "cancel")), ("package_id", "=", package.id), ("is_outbound_scanned", "=", True), ("outbound_scanned_quantity", ">", 0)])
                package_quants = quant_model.sudo().search([("package_id", "=", package.id), ("location_id.usage", "=", "internal"), ("quantity", ">", 0)])
                stock_quantities = {}
                scanned_quantities = {}
                product_by_key = {}
                for quant in package_quants:
                    key = (quant.location_id.id, quant.product_id.id, quant.lot_id.id, quant.owner_id.id)
                    stock_quantities[key] = stock_quantities.get(key, 0.0) + quant.quantity
                    product_by_key[key] = quant.product_id
                for line in scanned_lines:
                    key = (line.location_id.id, line.product_id.id, line.lot_id.id, line.owner_id.id)
                    scanned_quantities[key] = scanned_quantities.get(key, 0.0) + line.outbound_scanned_quantity
                    product_by_key[key] = line.product_id
                complete = bool(stock_quantities) and set(stock_quantities) == set(scanned_quantities)
                if complete:
                    for key, stock_quantity in stock_quantities.items():
                        if float_compare(stock_quantity, scanned_quantities[key], precision_rounding=product_by_key[key].uom_id.rounding) != 0:
                            complete = False
                            break
                if not complete:
                    move_line_model.browse(whole_lines.filtered(lambda line: line.package_id == package).ids).write({"result_package_id": False})

    def sync_outbound_charge_billing_object(self):
        for rec in self:
            if rec.picking_type_code != 'outgoing' or rec.state in ('done', 'cancel'):
                continue
            rec.move_line_ids.filtered(lambda line: line.state != 'cancel' and line.quantity > 0 and not line.outbound_charge_billing_object).write({'outbound_charge_billing_object': 'carton'})

    def button_validate(self):
        secondary_outbound_pickings = self.filtered(lambda rec: not self.env.context.get('skip_secondary_outbound_validation') and rec.picking_type_code == 'outgoing' and rec.project_id.outbound_palletization_enabled and rec.state not in ('done', 'cancel'))
        if secondary_outbound_pickings:
            if secondary_outbound_pickings != self:
                raise UserError(_('Pickings with different outbound completion workflows must be validated separately.'))
            preparation_pickings = secondary_outbound_pickings.filtered(lambda rec: rec.outbound_preparation_state != 'prepared')
            if preparation_pickings:
                for rec in preparation_pickings:
                    rec.sync_outbound_charge_billing_object()
                    rec.write({'outbound_preparation_state': 'prepared', 'outbound_prepared_by_id': self.env.user.id, 'outbound_prepared_at': fields.Datetime.now()})
                return True
            for rec in secondary_outbound_pickings:
                unconfirmed_move_lines = rec.move_line_ids.filtered(lambda line: line.state != 'cancel' and line.quantity > 0 and not line.secondary_outbound_confirmed)
                if unconfirmed_move_lines:
                    raise UserError(_('Complete secondary outbound confirmation before validating outgoing picking %s.') % rec.name)
        self.sync_outbound_charge_billing_object()
        result = super().button_validate()
        quant_model = self.env['stock.quant'].sudo()
        for rec in self:
            if rec.picking_type_id.code not in ('incoming', 'outgoing') or rec.state != 'done':
                continue
            package_records = rec.move_line_ids.mapped('package_id') | rec.move_line_ids.mapped('result_package_id')
            for package in package_records:
                if package.lifecycle_state == 'closed':
                    continue
                package_quant = quant_model.search([('package_id', '=', package.id), ('location_id.usage', '=', 'internal'), ('quantity', '>', 0)], limit=1)
                values = {}
                if package_quant:
                    if package.lifecycle_state != 'active':
                        values['lifecycle_state'] = 'active'
                    if rec.picking_type_id.code == 'incoming' and not package.lifecycle_start_datetime:
                        values['lifecycle_start_datetime'] = rec.date_done or fields.Datetime.now()
                elif package.lifecycle_state == 'active':
                    values.update({'lifecycle_state': 'consumed', 'consumed_datetime': rec.date_done or fields.Datetime.now()})
                if values:
                    package.write(values)
        return result
