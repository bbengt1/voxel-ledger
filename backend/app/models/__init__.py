"""ORM models. Importing here is how SQLAlchemy + Alembic discover tables."""

from app.core.db import Base
from app.models.audit import AuditLog
from app.models.auth import RefreshToken, Role, User
from app.models.custom_field import (
    CUSTOM_FIELD_ENTITY_TYPES,
    CustomField,
    CustomFieldType,
    FormTemplate,
    FormTemplateField,
)
from app.models.event import Event
from app.models.material import Material
from app.models.material_receipt import MaterialReceipt
from app.models.product import Product
from app.models.product_bom_item import ProductBomItem
from app.models.projection import ProjectionCursor, ProjectionTestEvent
from app.models.rate import Rate, RateKind
from app.models.reference_sequence import ReferenceSequence
from app.models.setting import Setting
from app.models.supply import Supply

__all__ = [
    "AuditLog",
    "Base",
    "CUSTOM_FIELD_ENTITY_TYPES",
    "CustomField",
    "CustomFieldType",
    "Event",
    "FormTemplate",
    "FormTemplateField",
    "Material",
    "MaterialReceipt",
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
