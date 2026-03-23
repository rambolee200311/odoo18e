from odoo import fields, models, _
from odoo.exceptions import ValidationError


class WaybillArrivalWizard(models.TransientModel):
    _name = "waybill.arrival.wizard"
    _description = "Waybill Arrival Wizard"

    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True, readonly=True)

    ata = fields.Date(string='ATA', tracking=True,required=True)
    #terminal_port = fields.Many2one('res.partner', string='Terminal of Port', tracking=True)
    terminal_a = fields.Many2one('res.partner', string='Terminal of Arrival', tracking=True)
    terminal_id = fields.Many2one("world.depot.port.node", string="Terminal", tracking=True)

    def action_confirm(self):
        for rec in self:
            if not rec.ata:
                raise ValidationError(_("Actual arrival date is required"))
            if not rec.terminal_id:
                raise ValidationError(_("Arrival port is required"))
            # if not rec.terminal_port:
            #     raise ValidationError(_("Port of loading is required"))
            if rec.waybill_id.state != "confirm":
                raise ValidationError(_("Only waybills in confirm status can confirm cargo arrival"))

            rec.waybill_id.write({
                "ata": rec.ata,
                #"terminal_port": rec.terminal_port.id,
                "terminal_id": rec.terminal_id.id,
                "arrival_confirm_user_id": self.env.user.id,
                "arrival_confirm_time": fields.Datetime.now(),
                "is_arrived": True,
            })
        return {"type": "ir.actions.act_window_close"}