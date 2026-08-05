from odoo import _, fields, models
from odoo.exceptions import ValidationError


class WaybillContainerBatchCreateWizard(models.TransientModel):
    _name = "waybill.container.batch.create.wizard"
    _description = "Waybill Container Batch Create Wizard"

    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill")
    clearance_id = fields.Many2one("operation.order.clearance", string="Clearance")
    container_numbers = fields.Text(string="Container Numbers", required=True)
    keep_existing_containers = fields.Boolean(string="Keep Existing Containers", default=True)

    def action_create_containers(self):
        env_container = self.env["world.depot.waybill.container"]
        created_count = 0

        for rec in self:
            if bool(rec.waybill_id) == bool(rec.clearance_id):
                raise ValidationError(_("Select either Waybill or Clearance."))

            container_numbers = [
                number.strip().upper()
                for number in (rec.container_numbers or "").splitlines()
                if number.strip()
            ]
            if not container_numbers:
                raise ValidationError(_("Container numbers are required."))

            if len(container_numbers) != len(set(container_numbers)):
                raise ValidationError(_("Duplicate container numbers were entered."))

            if rec.waybill_id:
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
                continue

            clearance = rec.clearance_id
            if clearance.state != "open":
                raise ValidationError(_("Containers can only be created for Open clearance."))

            if clearance.waybill_id:
                raise ValidationError(
                    _("Batch creation is only available for manual clearance without a waybill.")
                )

            container_ids = clearance.clearance_container_ids
            if rec.keep_existing_containers:
                existing_numbers = env_container.sudo().search([
                    ("id", "in", container_ids.ids),
                    ("container_number", "in", container_numbers),
                ]).mapped("container_number")
                if existing_numbers:
                    raise ValidationError(
                        _("Container numbers already exist: %s") % ", ".join(existing_numbers)
                    )
            else:
                if container_ids.filtered("waybill_id"):
                    raise ValidationError(
                        _("Waybill containers cannot be deleted from manual clearance.")
                    )

                other_clearance = self.env["operation.order.clearance"].sudo().search([
                    ("id", "!=", clearance.id),
                    ("clearance_container_ids", "in", container_ids.ids),
                ], limit=1)
                if other_clearance:
                    raise ValidationError(
                        _("Existing containers are linked to another clearance and cannot be deleted.")
                    )

                container_ids.unlink()

            new_container_ids = env_container.create([
                {"container_number": container_number}
                for container_number in container_numbers
            ])
            clearance.write({
                "clearance_container_ids": [(4, container.id) for container in new_container_ids],
            })
            clearance.write({
                "container_qty": len(clearance.clearance_container_ids),
            })
            created_count += len(new_container_ids)

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