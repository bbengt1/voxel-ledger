"""ORM models. Importing here is how SQLAlchemy + Alembic discover tables."""

from app.core.db import Base
from app.models.account import ACCOUNT_TYPE_VALUES, Account, AccountType
from app.models.account_balance import AccountBalance
from app.models.accounting_period import (
    ACCOUNTING_PERIOD_STATE_VALUES,
    AccountingPeriod,
    AccountingPeriodState,
)
from app.models.approval_request import (
    APPROVAL_STATE_VALUES,
    ApprovalRequest,
    ApprovalState,
)
from app.models.attachment import Attachment
from app.models.audit import AuditLog
from app.models.auth import RefreshToken, Role, User
from app.models.budget import Budget
from app.models.camera import CAMERA_KIND_VALUES, Camera, CameraKind
from app.models.credit_note import (
    CREDIT_NOTE_STATE_VALUES,
    DEBIT_NOTE_STATE_VALUES,
    CreditNote,
    CreditNoteState,
    DebitNote,
    DebitNoteState,
)
from app.models.custom_field import (
    CUSTOM_FIELD_ENTITY_TYPES,
    CustomField,
    CustomFieldType,
    FormTemplate,
    FormTemplateField,
)
from app.models.customer import (
    CUSTOMER_STATE_VALUES,
    Customer,
    CustomerContact,
    CustomerState,
)
from app.models.customer_credit import (
    CUSTOMER_CREDIT_KIND_VALUES,
    CustomerCreditBalance,
    CustomerCreditKind,
    CustomerCreditTransaction,
)
from app.models.division import Division
from app.models.email_message import (
    EMAIL_KIND_VALUES,
    EMAIL_STATE_VALUES,
    EmailKind,
    EmailMessage,
    EmailState,
)
from app.models.event import Event
from app.models.inventory_location import InventoryLocation, InventoryLocationKind
from app.models.inventory_on_hand import InventoryOnHand
from app.models.inventory_transaction import InventoryTransaction
from app.models.invoice import (
    INVOICE_ITEM_KIND_VALUES,
    INVOICE_STATE_VALUES,
    Invoice,
    InvoiceItem,
    InvoiceItemKind,
    InvoiceState,
)
from app.models.job import JOB_STATE_VALUES, Job, JobState
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.models.material import Material
from app.models.material_receipt import MaterialReceipt
from app.models.note import Note
from app.models.payment import (
    PAYMENT_METHOD_VALUES,
    PAYMENT_STATE_VALUES,
    Payment,
    PaymentApplication,
    PaymentMethod,
    PaymentState,
)
from app.models.plate import Plate
from app.models.pos_cart import (
    POS_CART_STATE_VALUES,
    PosCart,
    PosCartItem,
    PosCartState,
)
from app.models.printer import PRINTER_TYPE_VALUES, Printer, PrinterType
from app.models.printer_history_event import (
    PRINTER_EVENT_KIND_VALUES,
    PrinterEventKind,
    PrinterHistoryEvent,
)
from app.models.product import Product
from app.models.product_bom_item import ProductBomItem
from app.models.production_order import (
    PRODUCTION_ORDER_STATE_VALUES,
    ProductionOrder,
    ProductionOrderJob,
    ProductionOrderState,
)
from app.models.projection import ProjectionCursor, ProjectionTestEvent
from app.models.quote import (
    QUOTE_ITEM_KIND_VALUES,
    QUOTE_STATE_VALUES,
    Quote,
    QuoteItem,
    QuoteItemKind,
    QuoteState,
)
from app.models.rate import Rate, RateKind
from app.models.recurring_invoice import (
    RECURRING_CADENCE_KIND_VALUES,
    RECURRING_TEMPLATE_STATE_VALUES,
    RecurringCadenceKind,
    RecurringInvoiceItemKind,
    RecurringInvoiceTemplate,
    RecurringInvoiceTemplateItem,
    RecurringTemplateState,
)
from app.models.reference_sequence import ReferenceSequence
from app.models.refund import (
    REFUND_KIND_VALUES,
    REFUND_STATE_VALUES,
    Refund,
    RefundItem,
    RefundKind,
    RefundState,
)
from app.models.sale import (
    SALE_ITEM_KIND_VALUES,
    SALE_STATE_VALUES,
    Sale,
    SaleItem,
    SaleItemKind,
    SaleState,
)
from app.models.sales_channel import (
    SALES_CHANNEL_FEE_MODEL_VALUES,
    SALES_CHANNEL_KIND_VALUES,
    SalesChannel,
    SalesChannelFeeModel,
    SalesChannelKind,
)
from app.models.setting import Setting
from app.models.shipment import SHIPMENT_STATE_VALUES, Shipment, ShipmentState
from app.models.supply import Supply

__all__ = [
    "ACCOUNTING_PERIOD_STATE_VALUES",
    "ACCOUNT_TYPE_VALUES",
    "APPROVAL_STATE_VALUES",
    "Account",
    "AccountBalance",
    "AccountType",
    "AccountingPeriod",
    "AccountingPeriodState",
    "ApprovalRequest",
    "ApprovalState",
    "Attachment",
    "AuditLog",
    "Base",
    "Budget",
    "CAMERA_KIND_VALUES",
    "CUSTOM_FIELD_ENTITY_TYPES",
    "Camera",
    "CameraKind",
    "CUSTOMER_STATE_VALUES",
    "CustomField",
    "CustomFieldType",
    "Customer",
    "CustomerContact",
    "CustomerState",
    "Division",
    "EMAIL_KIND_VALUES",
    "EMAIL_STATE_VALUES",
    "EmailKind",
    "EmailMessage",
    "EmailState",
    "Event",
    "FormTemplate",
    "FormTemplateField",
    "InventoryLocation",
    "InventoryLocationKind",
    "InventoryOnHand",
    "InventoryTransaction",
    "CREDIT_NOTE_STATE_VALUES",
    "CUSTOMER_CREDIT_KIND_VALUES",
    "CreditNote",
    "CreditNoteState",
    "CustomerCreditBalance",
    "CustomerCreditKind",
    "CustomerCreditTransaction",
    "DEBIT_NOTE_STATE_VALUES",
    "DebitNote",
    "DebitNoteState",
    "INVOICE_ITEM_KIND_VALUES",
    "INVOICE_STATE_VALUES",
    "Invoice",
    "InvoiceItem",
    "InvoiceItemKind",
    "InvoiceState",
    "PAYMENT_METHOD_VALUES",
    "PAYMENT_STATE_VALUES",
    "Payment",
    "PaymentApplication",
    "PaymentMethod",
    "PaymentState",
    "JOB_STATE_VALUES",
    "Job",
    "JobState",
    "JournalEntry",
    "JournalLine",
    "Material",
    "MaterialReceipt",
    "Note",
    "PRINTER_EVENT_KIND_VALUES",
    "PRINTER_TYPE_VALUES",
    "Plate",
    "POS_CART_STATE_VALUES",
    "PosCart",
    "PosCartItem",
    "PosCartState",
    "Printer",
    "PrinterEventKind",
    "PrinterHistoryEvent",
    "PrinterType",
    "PRODUCTION_ORDER_STATE_VALUES",
    "Product",
    "ProductBomItem",
    "ProductionOrder",
    "ProductionOrderJob",
    "ProductionOrderState",
    "ProjectionCursor",
    "ProjectionTestEvent",
    "QUOTE_ITEM_KIND_VALUES",
    "QUOTE_STATE_VALUES",
    "Quote",
    "QuoteItem",
    "QuoteItemKind",
    "QuoteState",
    "RECURRING_CADENCE_KIND_VALUES",
    "RECURRING_TEMPLATE_STATE_VALUES",
    "RecurringCadenceKind",
    "RecurringInvoiceItemKind",
    "RecurringInvoiceTemplate",
    "RecurringInvoiceTemplateItem",
    "RecurringTemplateState",
    "REFUND_KIND_VALUES",
    "REFUND_STATE_VALUES",
    "Rate",
    "RateKind",
    "ReferenceSequence",
    "Refund",
    "RefundItem",
    "RefundKind",
    "RefundState",
    "RefreshToken",
    "Role",
    "SALE_ITEM_KIND_VALUES",
    "SALE_STATE_VALUES",
    "SALES_CHANNEL_FEE_MODEL_VALUES",
    "SALES_CHANNEL_KIND_VALUES",
    "Sale",
    "SaleItem",
    "SaleItemKind",
    "SaleState",
    "SalesChannel",
    "SalesChannelFeeModel",
    "SalesChannelKind",
    "SHIPMENT_STATE_VALUES",
    "Setting",
    "Shipment",
    "ShipmentState",
    "Supply",
    "User",
]
