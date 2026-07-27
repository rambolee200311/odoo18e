from odoo import _, fields, models
from odoo.exceptions import ValidationError


class WaybillContainerBatchCreateWizard(models.TransientModel):
    _name = "waybill.container.batch.create.wizard"
    _description = "Waybill Container Batch Create Wizard"

    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True)
    container_numbers = fields.Text(string="Container Numbers", required=True)
    keep_existing_containers = fields.Boolean(string="Keep Existing Containers", default=True)

    def action_create_containers(self):
        env_container = self.env["world.depot.waybill.container"]
        created_count = 0

        for rec in self:
            container_numbers = [
                number.strip().upper()
                for number in (rec.container_numbers or "").splitlines()
                if number.strip()
            ]
            if not container_numbers:
                raise ValidationError(_("Container numbers are required."))

            if len(container_numbers) != len(set(container_numbers)):
                raise ValidationError(_("Duplicate container numbers were entered."))

            if rec.keep_existing_containers:
                existing_numbers = env_container.sudo().search([
                    ("waybill_id", "=", rec.waybill_id.id),
                    ("container_number", "in", container_numbers),
                ]).mapped("container_number")
                if existing_numbers:
                    raise ValidationError(
                        _("Container numbers already exist: %s") % ", ".join(existing_numbers)
                    )
            else:
                rec.waybill_id.container_ids.unlink()

            env_container.create([
                {
                    "waybill_id": rec.waybill_id.id,
                    "container_number": container_number,
                }
                for container_number in container_numbers
            ])
            created_count += len(container_numbers)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Batch Create Containers"),
                "message": _("%s containers created.") % created_count,
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "reload",
                },
            },
        }