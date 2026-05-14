"""v1 API router aggregate.

Business endpoints will hang off this router as bounded-context modules
land. The health endpoint is intentionally mounted at the app root by
`app.main` (unversioned infra contract), so it is not included here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin import admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.materials import router as materials_router
from app.api.v1.products import router as products_router
from app.api.v1.settings import router as settings_router
from app.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(settings_router)
api_router.include_router(users_router)
api_router.include_router(materials_router)
api_router.include_router(products_router)
