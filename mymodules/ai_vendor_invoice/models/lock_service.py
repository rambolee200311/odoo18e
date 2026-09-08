# © 2024 Wukong Digital. License LGPL-3.
# Dedicated lock utilities wrapping SELECT FOR UPDATE.
# Design constraint: only two named functions (lock_task / lock_attempt) to
# eliminate dynamic SQL identifier injection risk (see TDD §13 risk table).
from odoo import models


class WdLockService(models.AbstractModel):
    """
    Stateless lock-utility service.
    Call via: self.env["wd.lock.service"].lock_task(task_id)
    Locks are held for the duration of the surrounding Odoo transaction and
    released automatically on commit or rollback.
    T-002: NEVER call these helpers while holding an external AI HTTP connection.
    """

    _name = "wd.lock.service"
    _description = "Row-Level Lock Utilities (SELECT FOR UPDATE)"

    def lock_task(self, task_id: int):
        """
        Acquire an exclusive row-lock on vendor.invoice.import.task.
        Safe: uses parameterised query; no dynamic identifier.
        Returns a browseable recordset for immediate use.
        """
        self.env.cr.execute(
            "SELECT id FROM vendor_invoice_import_task WHERE id = %s FOR UPDATE",
            (task_id,),
        )
        return self.env["vendor.invoice.import.task"].browse(task_id)

    def lock_attempt(self, attempt_id: int):
        """
        Acquire an exclusive row-lock on vendor.invoice.import.parse.attempt.
        Safe: uses parameterised query; no dynamic identifier.
        Returns a browseable recordset for immediate use.
        """
        self.env.cr.execute(
            "SELECT id FROM vendor_invoice_import_parse_attempt"
            " WHERE id = %s FOR UPDATE",
            (attempt_id,),
        )
        return self.env["vendor.invoice.import.parse.attempt"].browse(attempt_id)
