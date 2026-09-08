# © 2024 Wukong Digital. License LGPL-3.
from odoo import fields, models


class VendorInvoiceImportPageArtifact(models.Model):
    _name = "vendor.invoice.import.page.artifact"
    _description = "AI Parse Page Artifact"
    _order = "parse_attempt_id, page_no, id"

    parse_attempt_id = fields.Many2one(
        "vendor.invoice.import.parse.attempt",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="parse_attempt_id.task_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    page_no = fields.Integer(required=True, readonly=True)
    image_attachment_id = fields.Many2one(
        "ir.attachment",
        ondelete="set null",
        readonly=True,
        groups=(
            "ai_vendor_invoice.group_reviewer,"
            "ai_vendor_invoice.group_config_manager"
        ),
    )
    mime_type = fields.Char(readonly=True)
    checksum = fields.Char(readonly=True, index=True)
    byte_size = fields.Integer(readonly=True)
    rendered_at = fields.Datetime(readonly=True)
    image_preview = fields.Binary(
        related="image_attachment_id.datas",
        string="Page Preview",
        readonly=True,
        groups=(
            "ai_vendor_invoice.group_reviewer,"
            "ai_vendor_invoice.group_config_manager"
        ),
    )
    preview_status = fields.Selection(
        [
            ("generated", "GENERATED"),
            ("not_available_for_historical_attempt", "NOT_AVAILABLE_FOR_HISTORICAL_ATTEMPT"),
        ],
        string="Preview Status",
        compute="_compute_preview_status",
    )

    def _compute_preview_status(self):
        for artifact in self:
            artifact.preview_status = (
                "generated"
                if artifact.image_attachment_id
                else "not_available_for_historical_attempt"
            )

    _sql_constraints = [
        (
            "attempt_page_unique",
            "unique(parse_attempt_id, page_no)",
            "A parse attempt can only have one artifact for each page.",
        ),
        (
            "page_no_positive",
            "check(page_no > 0)",
            "Page number must be positive.",
        ),
    ]
