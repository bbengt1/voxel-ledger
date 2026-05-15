"""v1 API router aggregate.

Business endpoints will hang off this router as bounded-context modules
land. The health endpoint is intentionally mounted at the app root by
`app.main` (unversioned infra contract), so it is not included here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.accounting_periods import router as accounting_periods_router
from app.api.v1.accounts import router as accounts_router
from app.api.v1.admin import admin_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.attachments import router as attachments_router
from app.api.v1.auth import router as auth_router
from app.api.v1.bom import router as bom_router
from app.api.v1.budgets import router as budgets_router
from app.api.v1.cameras import router as cameras_router
from app.api.v1.custom_fields import router as custom_fields_router
from app.api.v1.divisions import router as divisions_router
from app.api.v1.form_templates import router as form_templates_router
from app.api.v1.inventory_alerts import router as inventory_alerts_router
from app.api.v1.inventory_locations import router as inventory_locations_router
from app.api.v1.inventory_on_hand import router as inventory_on_hand_router
from app.api.v1.inventory_transactions import router as inventory_transactions_router
from app.api.v1.journal_entries import router as journal_entries_router
from app.api.v1.materials import router as materials_router
from app.api.v1.notes import router as notes_router
from app.api.v1.printers import router as printers_router
from app.api.v1.products import router as products_router
from app.api.v1.rates import router as rates_router
from app.api.v1.settings import router as settings_router
from app.api.v1.supplies import router as supplies_router
from app.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(accounting_periods_router)
api_router.include_router(accounts_router)
api_router.include_router(admin_router)
api_router.include_router(approvals_router)
api_router.include_router(attachments_router)
api_router.include_router(budgets_router)
api_router.include_router(divisions_router)
api_router.include_router(settings_router)
api_router.include_router(users_router)
api_router.include_router(custom_fields_router)
api_router.include_router(form_templates_router)
api_router.include_router(inventory_alerts_router)
api_router.include_router(inventory_locations_router)
api_router.include_router(inventory_on_hand_router)
api_router.include_router(inventory_transactions_router)
api_router.include_router(journal_entries_router)
api_router.include_router(materials_router)
api_router.include_router(notes_router)
api_router.include_router(printers_router)
api_router.include_router(cameras_router)
api_router.include_router(products_router)
api_router.include_router(bom_router)
api_router.include_router(rates_router)
api_router.include_router(supplies_router)
