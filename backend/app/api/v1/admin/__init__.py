"""Admin endpoints (owner-only). Mounted under /api/v1/admin."""

from fastapi import APIRouter

from app.api.v1.admin.audit_log import router as audit_log_router
from app.api.v1.admin.events import router as events_router
from app.api.v1.admin.printer_monitor import router as printer_monitor_router
from app.api.v1.admin.quickbooks import router as quickbooks_router
from app.api.v1.admin.quickbooks_decommission import router as quickbooks_decommission_router
from app.api.v1.admin.quickbooks_mapping import router as quickbooks_mapping_router
from app.api.v1.admin.quickbooks_reconciliation import router as quickbooks_reconciliation_router
from app.api.v1.admin.quickbooks_sync import router as quickbooks_sync_router
from app.api.v1.admin.reference_sequences import router as reference_sequences_router
from app.api.v1.admin.workers import router as workers_router

admin_router = APIRouter(prefix="/admin", tags=["admin"])
admin_router.include_router(events_router)
admin_router.include_router(reference_sequences_router)
admin_router.include_router(audit_log_router)
admin_router.include_router(printer_monitor_router)
admin_router.include_router(workers_router)
admin_router.include_router(quickbooks_router)
admin_router.include_router(quickbooks_mapping_router)
admin_router.include_router(quickbooks_sync_router)
admin_router.include_router(quickbooks_reconciliation_router)
admin_router.include_router(quickbooks_decommission_router)
