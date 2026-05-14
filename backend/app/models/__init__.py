"""ORM models. Importing here is how SQLAlchemy + Alembic discover tables."""

from app.core.db import Base
from app.models.attachment import Attachment
from app.models.audit import AuditLog
from app.models.auth import RefreshToken, Role, User
from app.models.event import Event
from app.models.material import Material
from app.models.material_receipt import MaterialReceipt
from app.models.note import Note
from app.models.product import Product
from app.models.product_bom_item import ProductBomItem
from app.models.projection import ProjectionCursor, ProjectionTestEvent
from app.models.rate import Rate, RateKind
from app.models.reference_sequence import ReferenceSequence
from app.models.setting import Setting
from app.models.supply import Supply

__all__ = [
    "Attachment",
    "AuditLog",
    "Base",
    "Event",
    "Material",
    "MaterialReceipt",
    "Note",
    "Product",
    "ProductBomItem",
    "ProjectionCursor",
    "ProjectionTestEvent",
    "Rate",
    "RateKind",
    "ReferenceSequence",
    "RefreshToken",
    "Role",
    "Setting",
    "Supply",
    "User",
]
