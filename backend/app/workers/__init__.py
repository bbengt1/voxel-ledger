"""Background worker entrypoints (Phase 1.2 framework + Phase 7.5 jobs).

This package collects async coroutines that are intended to run on a
schedule. Phase 1.2 stubbed the framework: a registry of named jobs +
their cron expressions. A process manager (cron, k8s CronJob, or an
in-process apscheduler) calls into ``run_job(name)`` on the configured
cadence.

Today the worker registry is intentionally minimal — the production
deploy invokes ``python -m app.workers.run <job_name>`` from an OS cron
job. Each job is a small async function that opens its own DB session
and commits per logical unit. Per-job exceptions are caught and logged
so a bad row does not block the rest.
"""

from __future__ import annotations

from app.workers.bank_auto_matcher import JOB_NAME as BANK_AUTO_MATCHER_JOB
from app.workers.late_fee_applicator import JOB_NAME as LATE_FEE_APPLICATOR_JOB
from app.workers.overdue_bill_marker import JOB_NAME as OVERDUE_BILL_MARKER_JOB
from app.workers.overdue_marker import JOB_NAME as OVERDUE_MARKER_JOB
from app.workers.recurring_bill_materializer import (
    JOB_NAME as RECURRING_BILL_MATERIALIZER_JOB,
)
from app.workers.recurring_invoice_materializer import (
    JOB_NAME as RECURRING_INVOICE_MATERIALIZER_JOB,
)
from app.workers.registry import WorkerJob, list_jobs, register_job, run_job

__all__ = [
    "BANK_AUTO_MATCHER_JOB",
    "LATE_FEE_APPLICATOR_JOB",
    "OVERDUE_BILL_MARKER_JOB",
    "OVERDUE_MARKER_JOB",
    "RECURRING_BILL_MATERIALIZER_JOB",
    "RECURRING_INVOICE_MATERIALIZER_JOB",
    "WorkerJob",
    "list_jobs",
    "register_job",
    "run_job",
]
