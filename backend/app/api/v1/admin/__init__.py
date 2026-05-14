"""Admin endpoints (owner-only). Mounted under /api/v1/admin."""

from fastapi import APIRouter

from app.api.v1.admin.events import router as events_router

admin_router = APIRouter(prefix="/admin", tags=["admin"])
admin_router.include_router(events_router)
