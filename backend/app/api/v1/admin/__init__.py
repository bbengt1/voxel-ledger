"""Admin endpoints (owner-only). Mounted under /api/v1/admin."""

from fastapi import APIRouter

from app.api.v1.admin.audit_log import router as audit_log_router
from app.api.v1.admin.events import router as events_router
from app.api.v1.admin.printer_monitor import router as printer_monitor_router
from app.api.v1.admin.reference_sequences import router as reference_sequences_router

admin_router = APIRouter(prefix="/admin", tags=["admin"])
admin_router.include_router(events_router)
admin_router.include_router(reference_sequences_router)
admin_router.include_router(audit_log_router)
admin_router.include_router(printer_monitor_router)
