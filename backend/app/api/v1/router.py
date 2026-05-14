"""v1 API router aggregate.

Business endpoints will hang off this router as bounded-context modules
land. The health endpoint is intentionally mounted at the app root by
`app.main` (unversioned infra contract), so it is not included here.
"""

from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter()
