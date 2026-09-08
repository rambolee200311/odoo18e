# © 2024 Wukong Digital. License LGPL-3.
"""Task-level timeout recovery for queue workers that stopped responding."""

from odoo import _, fields


def reconcile_failed_queue_attempts(env):
    """Converge attempts whose queue job reached a terminal failed state."""
    attempts = env["vendor.invoice.import.parse.attempt"].search([
        ("status", "in", ("queued", "running")),
        ("queue_job_id.state", "=", "failed"),
    ])
    count = 0
    for candidate in attempts:
        with env.cr.savepoint():
            task = env["wd.lock.service"].lock_task(candidate.task_id.id)
            attempt = env["wd.lock.service"].lock_attempt(candidate.id)
            if (task.state != "parsing"
                    or task.current_parse_attempt_id != attempt
                    or attempt.status not in ("queued", "running")
                    or not attempt.queue_job_id
                    or attempt.queue_job_id.state != "failed"):
                continue
            summary = _("The AI parsing job failed before it completed.")
            completed_at = fields.Datetime.now()
            attempt.write({
                "status": "failed",
                "finished_at": completed_at,
                "completed_at": completed_at,
                "error_message": summary,
                "error_summary": summary,
            })
            task.write({"state": "error"})
            env["vendor.invoice.import.log"].create({
                "task_id": task.id,
                "parse_attempt_id": attempt.id,
                "action": "queue_reconciliation",
                "snapshot_delta": "Converged an attempt after its queue job failed.",
            })
            count += 1
    return count


def check_parsing_timeout(env):
    """Mark overdue queued/running tasks and their current attempt as failed."""
    config = env["wd.system.config"].get_config()
    timeout = config.task_timeout
    now = fields.Datetime.from_string(fields.Datetime.now())
    count = 0

    candidates = env["vendor.invoice.import.task"].search([
        ("state", "=", "parsing"),
        ("enter_parsing_datetime", "!=", False),
    ])
    for candidate in candidates:
        entered = fields.Datetime.from_string(candidate.enter_parsing_datetime)
        if not entered or now - entered <= timeout:
            continue

        with env.cr.savepoint():
            task = env["wd.lock.service"].lock_task(candidate.id)
            task.ensure_one()
            if task.state != "parsing" or not task.enter_parsing_datetime:
                continue
            entered = fields.Datetime.from_string(task.enter_parsing_datetime)
            if not entered or now - entered <= timeout:
                continue
            attempt = task.current_parse_attempt_id
            if not attempt or attempt.status not in ("queued", "running"):
                continue
            if attempt.queue_job_id and attempt.queue_job_id.state == "started":
                env.cr.execute(
                    "SELECT 1 FROM queue_job_lock WHERE queue_job_id = %s",
                    (attempt.queue_job_id.id,),
                )
                if env.cr.fetchone():
                    continue
            attempt = env["wd.lock.service"].lock_attempt(attempt.id)
            summary = _("Task parsing timeout exceeded; worker did not complete.")
            completed_at = fields.Datetime.now()
            attempt.write({
                "status": "failed",
                "finished_at": completed_at,
                "completed_at": completed_at,
                "error_message": summary,
                "error_summary": summary,
            })
            task.write({"state": "error"})
            env["vendor.invoice.import.log"].create({
                "task_id": task.id,
                "parse_attempt_id": attempt.id,
                "action": "cron_timeout",
                "snapshot_delta": "Parsing lifecycle exceeded configured timeout.",
            })
            count += 1
    return count
