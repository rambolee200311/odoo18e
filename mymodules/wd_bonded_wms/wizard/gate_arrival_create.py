# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class GateArrivalCreate(models.TransientModel):
    _name = 'gate.arrival.create'
    _description = 'Wizard: Create Gate Arrival from T1 Declaration'

    customs_file_id = fields.Many2one('bonded.customs.file', string='T1 Customs Declaration',
                                      required=True,
                                      domain=[('declaration_type', '=', 't1_in'),
                                              ('state', '=', 'customs_approved')])
    container_no = fields.Char(string='Container Number', required=True)
    seal_no = fields.Char(string='Seal Number', required=True)
    carrier_id = fields.Many2one('res.partner', string='Carrier', required=True)
    plate_number = fields.Char(string='Truck Plate Number')
    driver_name = fields.Char(string='Driver Name')
    driver_phone = fields.Char(string='Driver Phone')
    arrival_datetime = fields.Datetime(string='Arrival Time', required=True, default=fields.Datetime.now)

    def action_create(self):
        self.ensure_one()
        gate = self.env['gate.arrival'].create({
            'customs_file_id': self.customs_file_id.id,
            'container_no': self.container_no,
            'seal_no': self.seal_no,
            'carrier_id': self.carrier_id.id,
            'plate_number': self.plate_number,
            'driver_name': self.driver_name,
            'driver_phone': self.driver_phone,
            'arrival_datetime': self.arrival_datetime,
            'handover_id': self.customs_file_id.handover_id.id if self.customs_file_id.handover_id else False,
            'state': 'pending',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'gate.arrival',
            'res_id': gate.id,
            'view_mode': 'form',
            'target': 'current',
        }