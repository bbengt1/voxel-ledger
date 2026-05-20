"""Schema registry for operational settings.

Each setting is a subclass of :class:`SettingSchema` declaring a
``key`` (namespaced dotted string), a ``default``, and a single ``value``
field whose Pydantic type is the storage type. The class itself is what
validates writes and provides defaults on reads.

Registration is decorator-driven. Importing this module is sufficient to
populate the registry because every concrete schema applies ``@register``
at class-definition time.

Decimal handling
----------------
For monetary / rate values we use ``pydantic.Decimal``. Storage encodes a
decimal as its canonical string (``Decimal.to_eng_string`` or ``str``);
the service layer round-trips through ``Decimal(stored_str)`` so precision
survives the JSON layer. Pydantic itself does the string-to-Decimal
coercion during validation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class UnknownSettingError(KeyError):
    """Lookup or write attempted against a key not in the registry."""


class SettingSchema(BaseModel):
    """Base for one typed operational setting.

    Subclasses MUST set the class variables ``key`` and ``default`` and
    declare a single ``value`` field whose annotation is the storage type.
    The schema is constructed as ``MySchema(value=raw)`` to validate; the
    validated ``.value`` attribute is what we persist (and the type the
    service returns to callers).
    """

    # Pydantic-side config: allow arbitrary types so dicts/decimals work
    # without bespoke encoders. Strict on extras — refuse unknown fields.
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    # ClassVar markers — concrete subclasses fill these in.
    key: ClassVar[str]
    default: ClassVar[Any]

    # Subclasses redeclare ``value`` with the actual storage type.
    value: Any


_REGISTRY: dict[str, type[SettingSchema]] = {}


def register(schema_cls: type[SettingSchema]) -> type[SettingSchema]:
    """Decorator: register a schema class under its ``key``.

    Re-registering the same class is a no-op (test re-imports). Two
    different classes claiming the same key is a programmer error and
    raises at import time.
    """
    key = getattr(schema_cls, "key", None)
    if not isinstance(key, str) or not key:
        raise TypeError(f"{schema_cls.__name__} must declare a non-empty class-level `key`")
    existing = _REGISTRY.get(key)
    if existing is schema_cls:
        return schema_cls
    if existing is not None:
        raise RuntimeError(
            f"setting key {key!r} already registered to "
            f"{existing.__name__}; cannot also bind {schema_cls.__name__}"
        )
    _REGISTRY[key] = schema_cls
    return schema_cls


def get_schema(key: str) -> type[SettingSchema]:
    """Return the registered schema for ``key`` or raise."""
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        raise UnknownSettingError(f"unknown setting key {key!r}") from exc


def all_schemas() -> dict[str, type[SettingSchema]]:
    """Snapshot of the registry, sorted by key for stable iteration."""
    return dict(sorted(_REGISTRY.items()))


def _is_registered(key: str) -> bool:
    return key in _REGISTRY


def _reset_for_tests() -> None:
    """Test helper. Not exported.

    Doesn't actually clear since concrete schemas register at import time
    and re-importing wouldn't repopulate after a wipe. Provided for
    symmetry only.
    """
    return None


# ---------------------------------------------------------------------------
# Concrete settings.
#
# Each class declares `key`, `default`, and a `value` field. The decorator
# wires it into the registry on import. Group by namespace so the registry
# stays easy to scan.
# ---------------------------------------------------------------------------


@register
class LaborRatePerHour(SettingSchema):
    """Hourly labor cost used by the cost engine (USD/hour)."""

    key: ClassVar[str] = "cost_engine.labor_rate_per_hour"
    default: ClassVar[Decimal] = Decimal("25.00")
    value: Decimal = Field(ge=0)


@register
class MachineRatePerHour(SettingSchema):
    """Hourly machine cost used by the cost engine (USD/hour)."""

    key: ClassVar[str] = "cost_engine.machine_rate_per_hour"
    default: ClassVar[Decimal] = Decimal("1.00")
    value: Decimal = Field(ge=0)


@register
class OverheadPercent(SettingSchema):
    """Overhead surcharge applied by the cost engine (percent, 0-100)."""

    key: ClassVar[str] = "cost_engine.overhead_percent"
    default: ClassVar[Decimal] = Decimal("15.00")
    value: Decimal = Field(ge=0, le=100)


@register
class PowerCostPerKwh(SettingSchema):
    """Power cost used by the cost engine (USD/kWh)."""

    key: ClassVar[str] = "cost_engine.power_cost_per_kwh"
    default: ClassVar[Decimal] = Decimal("0.12")
    value: Decimal = Field(ge=0)


@register
class DefaultMarginPercent(SettingSchema):
    """Default margin applied by quote/job pricing (percent, 0-100)."""

    key: ClassVar[str] = "cost_engine.default_margin_percent"
    default: ClassVar[Decimal] = Decimal("30.00")
    value: Decimal = Field(ge=0, le=100)


@register
class BarcodeScanPadding(SettingSchema):
    """Pad character prepended to short barcode scans at POS.

    Stored as a string so the operator can pick ``"0"``, ``""``, or even
    a multi-character prefix without changing the schema.
    """

    key: ClassVar[str] = "pos.barcode_scan_padding"
    default: ClassVar[str] = "0"
    value: str


@register
class AttachmentsStorageRoot(SettingSchema):
    """Filesystem root for uploaded attachments (Phase 2.6).

    Stored as a string so contributors can override in local dev to a
    path like ``./data/attachments`` (which should be gitignored). In
    prod we deploy with ``/srv/3d-print-sales/data/attachments``. The
    attachments service joins ``{YYYY}/{MM}/{uuid}-{slug}`` underneath.
    """

    key: ClassVar[str] = "attachments.storage_root"
    default: ClassVar[str] = "/srv/3d-print-sales/data/attachments"
    value: str = Field(min_length=1)


@register
class ReferencePaddingWidth(SettingSchema):
    """Per-prefix padding width for the reference-number allocator.

    Keys are prefixes (``S``, ``INV``, ``Q``, ``BILL``); values are the
    zero-padded numeric width. The allocator falls back to the schema
    default for any prefix not present in the stored dict.
    """

    key: ClassVar[str] = "reference.padding_width"
    default: ClassVar[dict[str, int]] = {
        "S": 4,
        "INV": 4,
        "Q": 4,
        "BILL": 4,
    }
    value: dict[str, int]


@register
class DefaultReceivingLocationId(SettingSchema):
    """Default ``inventory_location`` ID that material receipts land into.

    Phase 3.2 (#51). When a material receipt is recorded the receipt flow
    needs to know where the grams are physically arriving so it can stamp
    the matching ``inventory_transaction`` row. Set this to the workshop
    or staging location that wraps your receiving dock. If left ``None``,
    the receipt service falls back to "lowest-code active workshop
    location", and finally raises ``InventoryConfigError`` if none exists.

    The value type is ``uuid.UUID | None``. Pydantic validates that
    strings are well-formed UUIDs on write; the settings service
    (de)serializes through the schema so the round-trip through JSON
    yields a real ``UUID`` instance on read.
    """

    key: ClassVar[str] = "inventory.default_receiving_location_id"
    default: ClassVar[uuid.UUID | None] = None
    # Stored as a string in the JSON column. Pydantic coerces "<uuid>"
    # back to ``UUID`` on read because the field annotation is
    # ``uuid.UUID``. The settings service's ``_serialize_for_storage``
    # casts our UUID to str via the dict-recursion path below.
    value: uuid.UUID | None = None


@register
class JournalEntryApprovalThreshold(SettingSchema):
    """USD threshold above which a journal entry routes to the approval
    queue instead of posting directly (Phase 4.4, #67).

    Compared against the sum of debits on the proposed entry. Strict
    ``>`` — an entry whose total exactly equals the threshold posts
    normally.
    """

    key: ClassVar[str] = "accounting.journal_entry.approval_threshold"
    default: ClassVar[Decimal] = Decimal("1000.00")
    value: Decimal = Field(ge=0)


@register
class SalesPostingCogsAccountId(SettingSchema):
    """Default COGS expense account for sale-confirm postings (Phase 6.3, #95).

    Debited for the total FIFO cost of all product/job lines on a sale.
    Optional — if unset, ``CogsService.post_for_sale`` raises
    ``MissingSalesPostingAccountError`` with a clear "configure default
    sales-posting accounts" message.
    """

    key: ClassVar[str] = "sales_posting.cogs_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class SalesPostingDefaultInventoryAccountId(SettingSchema):
    """Default inventory asset account for sale-confirm postings (Phase 6.3, #95).

    Credited for the total FIFO cost of all product/job lines on a sale.
    Required for any sale that carries non-zero COGS — the COGS service
    raises ``MissingSalesPostingAccountError`` with a clear "configure
    default sales-posting accounts" message if unset.

    Decoupled from the COGS account: routing the inventory credit to the
    COGS account's parent (the prior shortcut) breaks any chart of
    accounts that doesn't nest inventory under COGS.
    """

    key: ClassVar[str] = "sales_posting.default_inventory_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class SalesPostingSalesTaxPayableAccountId(SettingSchema):
    """Default sales-tax-payable liability account (Phase 6.3, #95).

    Credited for the sale's ``tax_amount`` at confirm time. Only required
    when a sale carries non-zero tax.
    """

    key: ClassVar[str] = "sales_posting.sales_tax_payable_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class SalesPostingDefaultArAccountId(SettingSchema):
    """Default accounts-receivable asset account (Phase 6.3, #95).

    Debited for the sale's gross ``total_amount`` at confirm time when
    the operator hasn't yet implemented per-channel cash/AR routing.
    The Phase 6.4 payment-method work will refine this.
    """

    key: ClassVar[str] = "sales_posting.default_ar_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class SalesPostingDefaultCashAccountId(SettingSchema):
    """Default cash asset account (Phase 6.3, #95).

    Currently unused by the confirm path (AR is the default debit target)
    but registered alongside the other sales-posting keys so the registry
    surface is complete and the Phase 6.4 POS / payment flow can read it
    without an additional settings migration.
    """

    key: ClassVar[str] = "sales_posting.default_cash_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ShippingDefaultCarrier(SettingSchema):
    """Carrier slug used when ``create_shipment`` isn't given an explicit
    ``carrier_hint`` (Phase 6.6, #98).

    Defaults to ``"static_fallback"`` — generates a local packing-slip
    PDF with no tracking number and zero cost. Set to ``"stub"`` in tests
    or to ``"usps"`` / ``"ups"`` / ``"fedex"`` once a real carrier
    integration ships in a later phase.
    """

    key: ClassVar[str] = "shipping.default_carrier"
    default: ClassVar[str] = "static_fallback"
    value: str = Field(min_length=1)


@register
class ShippingShipFromAddress(SettingSchema):
    """The shop's ``ship_from`` address snapshotted onto every shipment
    at create time (Phase 6.6, #98).

    Stored as a JSON dict with these expected keys: ``name``, ``street1``,
    ``street2``, ``city``, ``region``, ``postal_code``, ``country``,
    ``phone``. Empty defaults so brand-new deployments don't blow up — the
    operator is expected to PUT this through the settings endpoint before
    shipping anything in earnest.
    """

    key: ClassVar[str] = "shipping.ship_from_address"
    default: ClassVar[dict[str, Any]] = {
        "name": "",
        "street1": "",
        "street2": "",
        "city": "",
        "region": "",
        "postal_code": "",
        "country": "US",
        "phone": "",
    }
    value: dict[str, Any]


@register
class ShippingLabelsStorageRoot(SettingSchema):
    """Filesystem root for rendered shipping-label PDFs (Phase 6.6, #98).

    Mirrors ``attachments.storage_root`` — stored as a string so dev /
    prod can override. The shipping service joins
    ``shipping-labels/{shipment_id}.pdf`` underneath. The local-FS
    backend writes directly; once an S3 backend lands, the same key is
    used as the S3 object key under a dedicated bucket prefix.
    """

    key: ClassVar[str] = "shipping.labels_storage_root"
    default: ClassVar[str] = "/srv/3d-print-sales/data/shipping-labels"
    value: str = Field(min_length=1)


@register
class ArDefaultRevenueAccountId(SettingSchema):
    """Default revenue account for invoice issuance (Phase 7.3, #111).

    Credited per-line at invoice issue time when the line's
    product/job revenue override (and customer default, and channel
    default) are all unset. Separate from
    ``sales_posting.default_revenue_account_id`` so the AR posting
    pathway can be configured independently from the Phase 6.3
    sale-confirm pathway.
    """

    key: ClassVar[str] = "ar.default_revenue_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ArDefaultArAccountId(SettingSchema):
    """Default AR account for invoice issuance (Phase 7.3, #111).

    Debited at invoice issue time for the gross invoice ``total_amount``
    when the customer/channel chain is unset.
    """

    key: ClassVar[str] = "ar.default_ar_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ArDefaultSalesTaxPayableAccountId(SettingSchema):
    """Default sales-tax-payable liability account for invoice issuance
    (Phase 7.3, #111).

    Credited at invoice issue time for the invoice's ``tax_amount`` when
    > 0. Only required when an issuing invoice carries non-zero tax.
    """

    key: ClassVar[str] = "ar.default_sales_tax_payable_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class InvoicesPdfStorageRoot(SettingSchema):
    """Filesystem root for rendered invoice PDFs (Phase 7.3, #111).

    Mirrors ``shipping.labels_storage_root``. The invoices service joins
    ``invoices/{invoice_id}.pdf`` underneath. The same local-FS backend
    is used; the abstraction lives in :mod:`app.services.files` so
    swapping to S3 later is a service-level concern.
    """

    key: ClassVar[str] = "invoices.pdf_storage_root"
    default: ClassVar[str] = "/srv/3d-print-sales/data/invoices"
    value: str = Field(min_length=1)


@register
class ArDefaultBankAccountId(SettingSchema):
    """Default cash / bank asset account credited on payment posting
    (Phase 7.4, #112).

    Debited at ``apply_payment`` time for the payment amount when the
    operator hasn't configured a per-method override in
    ``ar.payment_method_to_account``. Required for any payment to post.
    """

    key: ClassVar[str] = "ar.default_bank_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ArPaymentMethodToAccount(SettingSchema):
    """Per-payment-method override map for the bank-side account
    (Phase 7.4, #112).

    Maps ``payment.method`` value (``cash``, ``check``, ``ach``,
    ``wire``, ``card``, ``marketplace``, ``other``) to an account UUID.
    Resolution at posting time:

    1. Look up the method in this map.
    2. Fall through to ``ar.default_bank_account_id``.
    3. Raise ``MissingArPostingAccountError`` if neither resolves.

    UUIDs are stored as strings inside the JSON dict and coerced by the
    payments service on read.
    """

    key: ClassVar[str] = "ar.payment_method_to_account"
    default: ClassVar[dict[str, Any]] = {}
    value: dict[str, Any]


class EmailProvider(SettingSchema):
    """Outbound email provider selection (Phase 7.7, #115).

    ``static_file`` writes rendered emails to disk for local dev (default).
    ``smtp`` uses the SMTP settings below. ``ses`` is a stub placeholder.
    """

    key: ClassVar[str] = "email.provider"
    default: ClassVar[str] = "static_file"
    value: str = Field(min_length=1)


@register
class EmailSmtpHost(SettingSchema):
    """SMTP relay hostname. Empty disables SMTP and forces static-file."""

    key: ClassVar[str] = "email.smtp_host"
    default: ClassVar[str] = ""
    value: str = ""


@register
class EmailSmtpPort(SettingSchema):
    """SMTP relay port. 587 is the STARTTLS default."""

    key: ClassVar[str] = "email.smtp_port"
    default: ClassVar[int] = 587
    value: int = Field(ge=1, le=65535)


@register
class EmailSmtpUsername(SettingSchema):
    """SMTP username (often the from-address itself)."""

    key: ClassVar[str] = "email.smtp_username"
    default: ClassVar[str] = ""
    value: str = ""


@register
class EmailSmtpPasswordSecret(SettingSchema):
    """SMTP password / API key. Opaque — redacted from event diffs.

    Follows the Phase 5.1 ``moonraker_api_key`` pattern. The
    ``settings.SettingChanged`` event for this key substitutes ``"***"``
    in both ``old_value`` and ``new_value`` so the event log never
    contains the real secret. See ``SettingsService.set``.
    """

    key: ClassVar[str] = "email.smtp_password_secret"
    default: ClassVar[str] = ""
    value: str = ""


@register
class EmailFromAddress(SettingSchema):
    """Default ``From:`` address on outbound emails."""

    key: ClassVar[str] = "email.from_address"
    default: ClassVar[str] = "no-reply@example.com"
    value: str = Field(min_length=1)


@register
class EmailStorageRoot(SettingSchema):
    """Filesystem root for rendered email bodies + static-file outputs.

    Mirrors ``invoices.pdf_storage_root``. The email service joins
    ``emails/{email_id}/body.html`` and
    ``emails/{email_id}/static.eml`` underneath.
    """

    key: ClassVar[str] = "email.storage_root"
    default: ClassVar[str] = "/srv/3d-print-sales/data/emails"
    value: str = Field(min_length=1)


# Set of setting keys whose values are sensitive — redacted in event payloads.
SECRET_SETTING_KEYS: frozenset[str] = frozenset({"email.smtp_password_secret"})


@register
class RefundApprovalThreshold(SettingSchema):
    """USD threshold above which a refund routes to the approval queue
    (Phase 4.4, #67 — Phase 6 consumes this).

    Registered here so the registry surface stays complete; the sales
    refund flow will wire its read through ``SettingsService.get`` once
    it lands.
    """

    key: ClassVar[str] = "sales.refund.approval_threshold"
    default: ClassVar[Decimal] = Decimal("500.00")
    value: Decimal = Field(ge=0)


@register
class ArDefaultLateFeeIncomeAccountId(SettingSchema):
    """Default Late Fee Income account credited when a Phase 7.6 late fee
    debit note is issued.

    When unset the late-fee worker falls back to
    ``ar.default_revenue_account_id`` (same credit side as a regular
    invoice). Operators are encouraged to set a dedicated income account
    so reporting can distinguish late-fee income from sale revenue.
    """

    key: ClassVar[str] = "ar.default_late_fee_income_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ApDefaultExpenseAccountId(SettingSchema):
    """Default expense account debited at bill-issue time (Phase 8.1, #128).

    Registered here so the registry is complete for Phase 8.2 bills.
    Falls through ``vendor.default_expense_account_id`` first.
    """

    key: ClassVar[str] = "ap.default_expense_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ApDefaultApAccountId(SettingSchema):
    """Default AP liability account credited at bill-issue time
    (Phase 8.1, #128).

    Registered here so the registry is complete for Phase 8.2 bills.
    Falls through ``vendor.default_ap_account_id`` first.
    """

    key: ClassVar[str] = "ap.default_ap_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ApDefaultTaxExpenseAccountId(SettingSchema):
    """Default Dr account for the tax portion of a bill (Phase 8.2, #129).

    Debited at bill-issue time for ``bill.tax_amount`` when > 0. v2 keeps
    tax simple: tax-on-purchases hits an expense account (non-recoverable
    tax). Phase 9 may split into a recoverable-tax-asset path; until
    then, set this to the same account used for purchase tax expense.

    If a bill carries tax > 0 and this is unset, ``issue`` raises
    ``MissingApPostingAccountError`` (mirrors invoices' sales-tax-payable
    requirement).
    """

    key: ClassVar[str] = "ap.default_tax_expense_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class BillsPdfStorageRoot(SettingSchema):
    """Filesystem root for rendered bill PDFs (Phase 8.2, #129).

    Mirrors ``invoices.pdf_storage_root``. The bills router joins
    ``bills/{bill_id}.pdf`` underneath. The same local-FS backend in
    :mod:`app.services.files` is used; swap to S3 later as a
    service-level concern.
    """

    key: ClassVar[str] = "bills.pdf_storage_root"
    default: ClassVar[str] = "/srv/3d-print-sales/data/bills"
    value: str = Field(min_length=1)


@register
class ApDefaultBankAccountId(SettingSchema):
    """Default bank / cash asset account credited on bill-payment posting
    (Phase 8.3, #130).

    Credited at bill-payment posting time for the payment amount when the
    operator hasn't configured a per-method override in
    ``ap.payment_method_to_account``. Required for any bill payment to
    post. Mirrors the AR-side ``ar.default_bank_account_id`` (Phase 7.4).
    """

    key: ClassVar[str] = "ap.default_bank_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ApDefaultWithholdingProfileId(SettingSchema):
    """Default withholding profile applied to every vendor unless they
    set their own ``vendor.withholding_profile_id`` (Phase 9.7, #159).

    When unset and a vendor has no per-vendor profile, no withholding
    fires on bill-payment apply.
    """

    key: ClassVar[str] = "ap.default_withholding_profile_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ApPaymentMethodToAccount(SettingSchema):
    """Per-payment-method override map for the bank-side account on bill
    payments (Phase 8.3, #130).

    Maps ``bill_payment.method`` value (``cash``, ``check``, ``ach``,
    ``wire``, ``card``, ``other``) to an account UUID. Resolution at
    posting time:

    1. Look up the method in this map.
    2. Fall through to ``ap.default_bank_account_id``.
    3. Raise ``MissingApPostingAccountError`` if neither resolves.

    UUIDs are stored as strings inside the JSON dict and coerced by the
    bill-payments service on read. Mirrors AR-side
    ``ar.payment_method_to_account``.
    """

    key: ClassVar[str] = "ap.payment_method_to_account"
    default: ClassVar[dict[str, Any]] = {}
    value: dict[str, Any]


@register
class ArAgingBucketDays(SettingSchema):
    """Cut points for the AR aging report's day buckets (Phase 7.6, #114).

    Stored as a sorted list of positive integers. Default ``[30, 60, 90]``
    yields buckets ``[0-30, 31-60, 61-90, 91+]``. The aging report endpoint
    also accepts a ``?buckets=`` override per-request.
    """

    key: ClassVar[str] = "ar.aging_bucket_days"
    default: ClassVar[list[int]] = [30, 60, 90]
    value: list[int] = Field(default_factory=lambda: [30, 60, 90])


@register
class ApExpenseClaimApprovalThreshold(SettingSchema):
    """USD threshold at or above which an expense claim routes through
    the Phase 4.4 approval queue when submitted (Phase 8.7, #134).

    Compared against the claim's rolled-up ``total_amount`` at submit
    time. ``>=`` semantics — a claim whose total exactly equals the
    threshold creates an ApprovalRequest. Below the threshold the claim
    still goes to ``submitted`` for owner/bookkeeper review, but no
    ApprovalRequest is created.
    """

    key: ClassVar[str] = "ap.expense_claim_approval_threshold"
    default: ClassVar[Decimal] = Decimal("200.00")
    value: Decimal = Field(ge=0)


@register
class ApEmployeeReimbursableAccountId(SettingSchema):
    """Default Employee Reimbursable liability account credited on
    expense-claim approval (Phase 8.7, #134).

    Credited at claim-approve time for the claim's total. A subsequent
    Phase 8.3 ``bill_payment`` against this same account completes the
    reimbursement (the operator stamps it onto the claim via
    ``POST /expense-claims/{id}/mark-reimbursed``).

    Required to approve any expense claim — if unset the approve flow
    raises a clear "configure ap.employee_reimbursable_account_id" error.
    """

    key: ClassVar[str] = "ap.employee_reimbursable_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class BankingReconciliationRoundingTolerance(SettingSchema):
    """Rounding tolerance applied when comparing the statement vs book
    ending balance during a bank reconciliation (Phase 8.11, #138).

    A reconciliation may be finalized when
    ``|statement_ending_balance - book_ending_balance| <= tolerance``.
    Default is exact zero — set to e.g. ``0.01`` to tolerate one-cent
    rounding noise that occasionally creeps in from third-party feeds.
    """

    key: ClassVar[str] = "banking.reconciliation_rounding_tolerance"
    default: ClassVar[Decimal] = Decimal("0.00")
    value: Decimal = Field(ge=0)


@register
class ApAgingBucketDays(SettingSchema):
    """Cut points for the AP aging report's day buckets (Phase 8.4, #131).

    Stored as a sorted list of positive integers. Default ``[30, 60, 90]``
    yields buckets ``[0-30, 31-60, 61-90, 91+]``. The aging report endpoint
    also accepts a ``?buckets=`` override per-request. Mirror of
    ``ar.aging_bucket_days``.
    """

    key: ClassVar[str] = "ap.aging_bucket_days"
    default: ClassVar[list[int]] = [30, 60, 90]
    value: list[int] = Field(default_factory=lambda: [30, 60, 90])


@register
class SettlementsDefaultAdjustmentAccountId(SettingSchema):
    """Default account used for the adjustment leg of a settlement
    payout JE (Phase 9.9, #161).

    Marketplaces occasionally include a positive or negative adjustment
    on the payout (gift-card top-ups, dispute reversals, promo credits).
    The settlement post service routes those to this account: positive
    adjustments Cr it (income / contra-expense), negative ones Dr it
    (expense / shortfall). Unset means a settlement with a non-zero
    adjustment cannot be posted.
    """

    key: ClassVar[str] = "settlements.default_adjustment_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ReportsCogsAccountIds(SettingSchema):
    """List of account UUIDs treated as Cost of Goods Sold in the
    income statement (Phase 10.1, #176).

    Default ``[]`` — every expense account rolls up under "Operating
    expenses" until the operator flags specific accounts as COGS.
    """

    key: ClassVar[str] = "reports.cogs_account_ids"
    default: ClassVar[list[str]] = []
    value: list[str] = Field(default_factory=list)


@register
class ReportsRetainedEarningsAccountId(SettingSchema):
    """Equity account that absorbs current-period net income on the
    Balance Sheet until period-close (Phase 10.2, #177).

    When set, the balance-sheet service adds revenue - expense YTD
    through ``as_of`` onto this account's balance so the report
    balances before the operator manually closes P&L. Unset is fine —
    the report still computes correctly and surfaces an ``imbalance``
    line.
    """

    key: ClassVar[str] = "reports.retained_earnings_account_id"
    default: ClassVar[uuid.UUID | None] = None
    value: uuid.UUID | None = None


@register
class ReportsDepreciationExpenseAccountIds(SettingSchema):
    """Expense accounts whose Dr - Cr in a period is added back to net
    income on the cash-flow statement (Phase 10.3, #178).

    Includes amortization expense accounts too — the cash-flow report
    treats both as non-cash add-backs.
    """

    key: ClassVar[str] = "reports.depreciation_expense_account_ids"
    default: ClassVar[list[str]] = []
    value: list[str] = Field(default_factory=list)


@register
class ReportsWorkingCapitalAccounts(SettingSchema):
    """Accounts whose Δ over the period drives the operating-activities
    working-capital walk on the cash-flow statement (Phase 10.3, #178).

    Typical members: AR, inventory, prepaid expenses, AP, accrued
    liabilities. Sign handling is automatic — for any account class,
    cash impact of period activity = ``sum(credit) - sum(debit)``.
    """

    key: ClassVar[str] = "reports.working_capital_accounts"
    default: ClassVar[list[str]] = []
    value: list[str] = Field(default_factory=list)


@register
class ReportsInvestingAccounts(SettingSchema):
    """Accounts whose period activity rolls up under "Investing
    activities" on the cash-flow statement (Phase 10.3, #178).

    Typical members: fixed-asset accounts, intangible-asset accounts,
    long-term investments.
    """

    key: ClassVar[str] = "reports.investing_accounts"
    default: ClassVar[list[str]] = []
    value: list[str] = Field(default_factory=list)


@register
class ReportsFinancingAccounts(SettingSchema):
    """Accounts whose period activity rolls up under "Financing
    activities" on the cash-flow statement (Phase 10.3, #178).

    Typical members: long-term debt, owner contributions, dividends
    paid.
    """

    key: ClassVar[str] = "reports.financing_accounts"
    default: ClassVar[list[str]] = []
    value: list[str] = Field(default_factory=list)


@register
class ReportsCashAccounts(SettingSchema):
    """Cash + equivalent accounts whose Dr - Cr over the period is the
    "Net change in cash" line on the cash-flow statement (Phase 10.3,
    #178).

    The dashboard-KPIs service (#181) also reads this list for "Cash on
    hand".
    """

    key: ClassVar[str] = "reports.cash_accounts"
    default: ClassVar[list[str]] = []
    value: list[str] = Field(default_factory=list)


@register
class ReportsAiInsightsProvider(SettingSchema):
    """Which provider the AI-insights worker uses (Phase 10.7, #182).

    Values: ``"deterministic"`` (default — no API calls, used in
    tests and dev) / ``"anthropic"`` / ``"openai"``. The deterministic
    summarizer renders a non-empty narrative from the structured
    payload so the dashboard tile is always populated.
    """

    key: ClassVar[str] = "reports.ai_insights_provider"
    default: ClassVar[str] = "deterministic"
    value: str = Field(default="deterministic", min_length=1)


@register
class ReportsAiInsightsModel(SettingSchema):
    """Model identifier passed to the LLM provider (Phase 10.7, #182).

    Ignored by the deterministic provider. The shape depends on the
    provider — e.g. ``"claude-opus-4-7"`` for Anthropic, a model id
    for OpenAI.
    """

    key: ClassVar[str] = "reports.ai_insights_model"
    default: ClassVar[str] = "deterministic"
    value: str = Field(default="deterministic", min_length=1)


# ---------------------------------------------------------------------------
# Phase 11.2 - inbound webhook shared secrets (#194)
# ---------------------------------------------------------------------------


def _make_inbound_secret_schema(key_name: str, doc: str) -> type[SettingSchema]:
    """Build a setting-schema class for one inbound provider's shared secret.

    Each provider configures its own HMAC shared secret outside the
    application (in the provider's dashboard) and we mirror it here so
    the inbound verifier can recompute the signature.
    """

    class _Schema(SettingSchema):
        __doc__ = doc
        key: ClassVar[str] = key_name
        default: ClassVar[str] = ""
        value: str = Field(default="")

    _Schema.__name__ = "WebhookInboundSecret_" + key_name.replace(".", "_")
    return _Schema


register(
    _make_inbound_secret_schema(
        "webhooks.inbound.carrier.easypost.secret",
        "EasyPost webhook shared secret (HMAC-SHA256).",
    )
)
register(
    _make_inbound_secret_schema(
        "webhooks.inbound.carrier.shipstation.secret",
        "ShipStation webhook shared secret (HMAC-SHA256).",
    )
)
register(
    _make_inbound_secret_schema(
        "webhooks.inbound.marketplace.ebay.secret",
        "eBay marketplace webhook shared secret (HMAC-SHA256).",
    )
)
register(
    _make_inbound_secret_schema(
        "webhooks.inbound.marketplace.etsy.secret",
        "Etsy marketplace webhook shared secret (HMAC-SHA256).",
    )
)
register(
    _make_inbound_secret_schema(
        "webhooks.inbound.marketplace.shopify.secret",
        "Shopify marketplace webhook shared secret (HMAC-SHA256).",
    )
)
register(
    _make_inbound_secret_schema(
        "webhooks.inbound.marketplace.amazon.secret",
        "Amazon marketplace webhook shared secret (HMAC-SHA256).",
    )
)
