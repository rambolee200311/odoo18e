# © 2024 Wukong Digital. License LGPL-3.
import re

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


STATEMENT_STATES = [
    ("draft", "Draft"),
    ("confirmed", "Confirmed"),
    ("cancelled", "Cancelled"),
    ("bill_created", "Bill Created"),
]


class VendorInvoiceStatement(models.Model):
    _name = "vendor.invoice.statement"
    _description = "Vendor Invoice Human Statement"
    _order = "id desc"

    name = fields.Char(
        string="Statement Number",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code(
            "vendor.invoice.statement"
        ) or _("New"),
    )
    state = fields.Selection(
        selection=STATEMENT_STATES,
        string="Status",
        required=True,
        default="draft",
        index=True,
        copy=False,
    )
    task_id = fields.Many2one(
        "vendor.invoice.import.task",
        string="Import Task",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="task_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    source_parse_attempt_id = fields.Many2one(
        "vendor.invoice.import.parse.attempt",
        string="Source Parse Attempt",
        required=True,
        ondelete="restrict",
        index=True,
    )
    source_pdf_attachment_id = fields.Many2one(
        related="task_id.source_pdf_attachment_id",
        string="Source PDF",
        readonly=True,
    )
    source_pdf_filename = fields.Char(
        related="task_id.source_pdf_filename",
        string="File Name",
        readonly=True,
    )
    review_warnings = fields.Json(
        related="task_id.review_warnings",
        string="Review Warnings",
        readonly=True,
    )
    invoice_number = fields.Char(string="Invoice Number", required=True)
    invoice_number_normalized = fields.Char(
        string="Normalized Invoice Number",
        compute="_compute_business_identity",
        store=True,
        index=True,
        copy=False,
        readonly=True,
    )
    invoice_date = fields.Date(string="Invoice Date")
    supplier_id = fields.Many2one("res.partner", string="Supplier")
    supplier_name = fields.Char(string="Supplier")
    supplier_identity_key = fields.Char(
        string="Supplier Identity Key",
        compute="_compute_business_identity",
        store=True,
        index=True,
        copy=False,
        readonly=True,
    )
    currency_id = fields.Many2one("res.currency", string="Currency")
    total_amount = fields.Monetary(
        string="Total Amount",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        readonly=True,
    )
    total_tax = fields.Monetary(
        string="Total Tax",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        readonly=True,
    )
    subtotal = fields.Monetary(
        string="Subtotal",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        readonly=True,
    )
    overall_tax_rate = fields.Float(
        string="Overall Tax Rate",
        compute="_compute_totals",
        store=True,
        readonly=True,
    )
    note = fields.Text(string="Notes")
    vendor_bill_id = fields.Many2one(
        "account.move",
        string="Vendor Bill",
        ondelete="restrict",
        index=True,
        copy=False,
        readonly=True,
    )
    line_ids = fields.One2many(
        "vendor.invoice.statement.line",
        "statement_id",
        string="Statement Lines",
        copy=True,
    )

    _sql_constraints = [
        (
            "task_unique",
            "unique(task_id)",
            "A task can have only one human Statement.",
        ),
    ]

    def init(self):
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                vendor_invoice_statement_business_unique
            ON vendor_invoice_statement (
                company_id,
                supplier_identity_key,
                invoice_number_normalized
            )
            WHERE state != 'cancelled'
              AND supplier_identity_key IS NOT NULL
              AND invoice_number_normalized IS NOT NULL
            """
        )

    @api.depends("invoice_number", "supplier_id", "supplier_name")
    def _compute_business_identity(self):
        for statement in self:
            statement.invoice_number_normalized = self._normalize_invoice_number(
                statement.invoice_number
            )
            statement.supplier_identity_key = (
                "partner:%s" % statement.supplier_id.id
                if statement.supplier_id
                else self._normalize_supplier_name(statement.supplier_name)
            )

    @api.depends(
        "line_ids.amount",
        "line_ids.tax_amount",
        "line_ids.total_amount",
        "currency_id",
    )
    def _compute_totals(self):
        for statement in self:
            subtotal = sum(line.amount or 0.0 for line in statement.line_ids)
            total_tax = sum(line.tax_amount or 0.0 for line in statement.line_ids)
            total_amount = sum(line.total_amount or 0.0 for line in statement.line_ids)
            round_amount = statement.currency_id.round if statement.currency_id else lambda value: value
            statement.subtotal = round_amount(subtotal)
            statement.total_tax = round_amount(total_tax)
            statement.total_amount = round_amount(total_amount)
            statement.overall_tax_rate = (
                (total_tax / subtotal) * 100 if subtotal else 0.0
            )

    @staticmethod
    def _normalize_invoice_number(value):
        return re.sub(r"\s+", "", (value or "").strip().upper()) or False

    @staticmethod
    def _normalize_supplier_name(value):
        return re.sub(r"\s+", " ", (value or "").strip().upper()) or False

    def _check_business_duplicate(self, values, exclude_ids=()):
        self.env.flush_all()
        task = (
            self.env["vendor.invoice.import.task"].browse(values["task_id"])
            if values.get("task_id")
            else self
        )
        company_id = values.get("company_id") or task.company_id.id
        invoice_number = values.get("invoice_number", self.invoice_number)
        supplier_id = values.get("supplier_id", self.supplier_id.id)
        supplier_name = values.get("supplier_name", self.supplier_name)
        normalized_invoice = self._normalize_invoice_number(invoice_number)
        supplier_key = (
            "partner:%s" % supplier_id
            if supplier_id
            else self._normalize_supplier_name(supplier_name)
        )
        if not company_id or not normalized_invoice or not supplier_key:
            return
        duplicate = self.search([
            ("company_id", "=", company_id),
            ("supplier_identity_key", "=", supplier_key),
            ("invoice_number_normalized", "=", normalized_invoice),
            ("state", "!=", "cancelled"),
            ("id", "not in", list(exclude_ids)),
        ], limit=1)
        if duplicate:
            raise ValidationError(
                _(
                    "An active Statement already exists for this supplier and "
                    "invoice number: %s."
                ) % duplicate.name
            )

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(
            _("Statement records must be created through a Task aggregate command.")
        )

    def write(self, vals):
        if "state" in vals:
            raise AccessError(_("Statement state must be changed through a transition command."))
        if not self.env.user.has_group("ai_vendor_invoice.group_reviewer"):
            raise AccessError(
                _("Statement records must be changed through a Task aggregate command.")
            )
        if any(statement.state != "draft" for statement in self):
            raise ValidationError(_("Only draft Statements can be edited."))
        for statement in self:
            statement._check_business_duplicate(vals, exclude_ids=(statement.id,))
        return super().write(vals)

    def unlink(self):
        if any(statement.state != "draft" for statement in self):
            raise ValidationError(_("Only draft Statements can be deleted."))
        raise AccessError(
            _("Statement records must be deleted through a Task aggregate command.")
        )

    def action_cancel_statement(self):
        """Delegate cancellation to the owning Task aggregate."""
        self.ensure_one()
        return self.task_id.action_cancel_statement()

    def action_apply_ai_candidate_from_statement(self):
        """Apply the current ParseAttempt candidate from the business form."""
        self.ensure_one()
        return self.task_id.action_apply_ai_candidate_from_statement()

    def action_confirm_from_statement(self):
        """Confirm the current Statement through its owning Task aggregate."""
        self.ensure_one()
        return self.task_id.action_confirm_statement(
            self.task_id._statement_payload_from_record()
        )

    def action_open_import_task(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Task"),
            "res_model": "vendor.invoice.import.task",
            "view_mode": "form",
            "res_id": self.task_id.id,
            "target": "current",
        }

    def action_open_source_pdf(self):
        self.ensure_one()
        if not self.source_pdf_attachment_id:
            raise ValidationError(_("This Statement has no source PDF."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Source PDF"),
            "res_model": "ir.attachment",
            "view_mode": "form",
            "res_id": self.source_pdf_attachment_id.id,
            "target": "current",
        }

    def action_open_vendor_bill(self):
        self.ensure_one()
        if not self.vendor_bill_id:
            raise ValidationError(_("This Statement has no Vendor Bill."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor Bill"),
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": self.vendor_bill_id.id,
            "target": "current",
        }

    @api.model
    def _aggregate_create(self, vals):
        """Persist a validated aggregate command without exposing generic CRUD."""
        self._check_business_duplicate(vals)
        return super().create(vals)

    def _aggregate_write(self, vals):
        for statement in self:
            statement._check_business_duplicate(vals, exclude_ids=(statement.id,))
        return super().write(vals)

    def _aggregate_unlink(self):
        return super().unlink()


class VendorInvoiceStatementLine(models.Model):
    _name = "vendor.invoice.statement.line"
    _description = "Vendor Invoice Human Statement Line"
    _order = "sequence, id"

    statement_id = fields.Many2one(
        "vendor.invoice.statement",
        string="Statement",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(required=True, default=10)
    description = fields.Text(required=True)
    product_id = fields.Many2one("product.product", string="Product")
    quantity = fields.Float(default=1.0)
    price_unit = fields.Monetary(currency_field="currency_id")
    amount = fields.Monetary(required=True, currency_field="currency_id")
    tax_raw_text = fields.Char(string="Tax")
    tax_rate = fields.Float(string="Tax Rate")
    tax_amount = fields.Monetary(string="Tax Amount", currency_field="currency_id")
    total_amount = fields.Monetary(
        string="Total Amount",
        currency_field="currency_id",
    )
    reconciliation_clue = fields.Char(string="Reconciliation Clue")
    charge_details = fields.Text(string="Charge Details")
    tax_ids = fields.Many2many("account.tax", string="Taxes")
    reconciliation_clues = fields.Json(
        string="Reconciliation Clues",
        help="Generic label/value clues preserved for a future reconciliation flow.",
    )
    currency_id = fields.Many2one(
        related="statement_id.currency_id",
        store=True,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.user.has_group("ai_vendor_invoice.group_reviewer"):
            raise AccessError(_("Only an invoice reviewer can edit Statement lines."))
        for vals in vals_list:
            statement = self.env["vendor.invoice.statement"].browse(
                vals.get("statement_id")
            )
            if not statement or statement.state != "draft":
                raise ValidationError(_("Only lines of a draft Statement can be created."))
            vals.update(self._normalize_amount_values(vals, statement=statement))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.user.has_group("ai_vendor_invoice.group_reviewer"):
            raise AccessError(_("Only an invoice reviewer can edit Statement lines."))
        if any(line.statement_id.state != "draft" for line in self):
            raise ValidationError(_("Only lines of a draft Statement can be edited."))
        if {"amount", "tax_rate", "tax_amount", "total_amount"} & set(vals):
            if len(self) != 1:
                raise ValidationError(_("Amount fields must be edited on one line at a time."))
            vals = dict(vals)
            vals.update(self._normalize_amount_values(vals))
        return super().write(vals)

    def unlink(self):
        if not self.env.user.has_group("ai_vendor_invoice.group_reviewer"):
            raise AccessError(_("Only an invoice reviewer can delete Statement lines."))
        if any(line.statement_id.state != "draft" for line in self):
            raise ValidationError(_("Only lines of a draft Statement can be deleted."))
        return super().unlink()

    def _normalize_amount_values(self, vals, statement=None, driver=None):
        """Normalize one monetary driver and derive the remaining amounts."""
        monetary_fields = {"amount", "tax_rate", "tax_amount", "total_amount"}
        if not monetary_fields & set(vals):
            return {}
        line = self[:1]
        statement = statement or line.statement_id
        currency = (
            statement.currency_id or self.env.company.currency_id
            if statement
            else self.env.company.currency_id
        )
        round_amount = currency.round
        amount = float(vals.get("amount", line.amount if line else 0.0) or 0.0)
        tax_rate = float(vals.get("tax_rate", line.tax_rate if line else 0.0) or 0.0)
        tax_amount = float(
            vals.get("tax_amount", line.tax_amount if line else 0.0) or 0.0
        )
        total_amount = float(
            vals.get("total_amount", line.total_amount if line else 0.0) or 0.0
        )
        keys = {key for key in monetary_fields if vals.get(key) is not None}
        if driver:
            keys = {driver}
        if "amount" in keys:
            if "tax_rate" in keys:
                tax_amount = amount * tax_rate / 100
            elif "tax_amount" in keys:
                tax_rate = tax_amount / amount * 100 if amount else 0.0
            elif "total_amount" in keys:
                tax_amount = total_amount - amount
                tax_rate = tax_amount / amount * 100 if amount else 0.0
            else:
                tax_amount = amount * tax_rate / 100
        elif "tax_rate" in keys:
            tax_amount = amount * tax_rate / 100
        elif "tax_amount" in keys:
            tax_rate = tax_amount / amount * 100 if amount else 0.0
        elif "total_amount" in keys:
            tax_amount = total_amount - amount
            tax_rate = tax_amount / amount * 100 if amount else 0.0
        if not amount and abs(tax_amount) > currency.rounding / 2:
            raise ValidationError(
                _("Tax amount must be zero when untaxed amount is zero.")
            )
        tax_amount = round_amount(tax_amount)
        total_amount = round_amount(amount + tax_amount)
        return {
            "amount": amount,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total_amount": total_amount,
        }

    def _apply_amount_onchange(self, driver):
        for line in self:
            values = {
                field_name: line[field_name]
                for field_name in ("amount", "tax_rate", "tax_amount", "total_amount")
            }
            changed = line._normalize_amount_values(values, driver=driver)
            for field_name, value in changed.items():
                line[field_name] = value

    @api.onchange("amount")
    def _onchange_amount(self):
        self._apply_amount_onchange("amount")

    @api.onchange("tax_rate")
    def _onchange_tax_rate(self):
        self._apply_amount_onchange("tax_rate")

    @api.onchange("tax_amount")
    def _onchange_tax_amount(self):
        self._apply_amount_onchange("tax_amount")

    @api.onchange("total_amount")
    def _onchange_total_amount(self):
        self._apply_amount_onchange("total_amount")

    @api.model
    def _aggregate_create(self, vals):
        vals_list = vals if isinstance(vals, list) else [vals]
        normalized = []
        for values in vals_list:
            values = dict(values)
            statement = self.env["vendor.invoice.statement"].browse(
                values["statement_id"]
            )
            values.update(self._normalize_amount_values(values, statement=statement))
            normalized.append(values)
        return super().create(normalized)

    def _aggregate_unlink(self):
        return super().unlink()


def validate_statement_payload(payload):
    if not isinstance(payload, dict) or not payload.get("invoice_number"):
        raise ValidationError(_("A Statement requires an invoice number."))
    lines = payload.get("lines", [])
    if not isinstance(lines, list):
        raise ValidationError(_("Statement lines must be a list."))
    for line in lines:
        if not isinstance(line, dict) or not line.get("description"):
            raise ValidationError(_("Each Statement line requires a description."))
        if "amount" not in line:
            raise ValidationError(_("Each Statement line requires an amount."))
    return payload
