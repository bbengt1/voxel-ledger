"""ORM models. Importing here is how SQLAlchemy + Alembic discover tables."""

from app.core.db import Base
from app.models.account import ACCOUNT_TYPE_VALUES, Account, AccountType
from app.models.account_balance import AccountBalance
from app.models.attachment import Attachment
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
from app.models.inventory_location import InventoryLocation, InventoryLocationKind
from app.models.inventory_on_hand import InventoryOnHand
from app.models.inventory_transaction import InventoryTransaction
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
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
    "ACCOUNT_TYPE_VALUES",
    "Account",
    "AccountBalance",
    "AccountType",
    "Attachment",
    "AuditLog",
    "Base",
    "CUSTOM_FIELD_ENTITY_TYPES",
    "CustomField",
    "CustomFieldType",
    "Event",
    "FormTemplate",
    "FormTemplateField",
    "InventoryLocation",
    "InventoryLocationKind",
    "InventoryOnHand",
    "InventoryTransaction",
    "JournalEntry",
    "JournalLine",
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
