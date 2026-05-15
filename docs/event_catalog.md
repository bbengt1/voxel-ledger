# Event catalog

Every event type the system writes, organized by aggregate / bounded
context. Source of truth is `backend/app/events/types/`; this doc is a
human-readable index. For the system-wide framing of the event log see
[`architecture.md`](architecture.md). For the audit-projection
denormalization rules see the [audit excerpt whitelist](#audit-excerpt-whitelist)
section at the bottom.

Conventions used in the tables below:

- **Type** is the fully-qualified type string (the dotted aggregate
  prefix plus the PascalCase event name).
- **Payload** lists field names + types lifted from the Pydantic model.
  Decimal-valued fields are serialized as canonical strings.
- **Emitted by** names the service module(s) under `backend/app/services/`.
- **Subscribed by** names projection handlers under
  `backend/app/projections/`. Every event is also picked up by the
  wildcard `audit_log_projection` — "audit only" means that's the only
  subscriber.

## `auth.*` — login / logout / refresh family

Aggregate type: `user` (or the zero-UUID sentinel for anonymous events).
All payloads inherit an optional `ip: str | None` field. Issues: #15, #24.

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `auth.LoginSucceeded` | Password verified, tokens minted. | `email: str`, `user_id: uuid` | `auth.py` | audit only |
| `auth.LoginFailed` | Wrong password or unknown email. | `email: str`, `reason: Literal["unknown_user","bad_password"]` | `auth.py` | audit only |
| `auth.LoginInactive` | Correct password but the account is deactivated. | `email: str` | `auth.py` | audit only |
| `auth.RefreshRotated` | Refresh token used, new pair minted. | `user_id: uuid` | `auth.py` | audit only |
| `auth.FamilyRevoked` | Refresh-token reuse detected or invalid refresh — entire family burned. | `reason: Literal["reuse_detected","invalid_refresh"]`, `user_id: uuid | None` | `auth.py` | audit only |
| `auth.LoggedOut` | Caller hit the logout endpoint. | `user_id: uuid | None` | `auth.py` | audit only |
| `auth.RateLimited` | Login rate limit tripped. | `endpoint: Literal["login"]` | `auth.py` | audit only |

## `users.*` — user lifecycle

Aggregate type: `user`. `actor_user_id` on the event row is the admin
performing the action. Payloads never carry passwords or hashes. Issue: #26.

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `users.UserCreated` | Admin created a user. | `user_id: uuid`, `email: str`, `full_name: str`, `role: str` | `users.py` | audit only |
| `users.UserUpdated` | Admin changed profile or role. | `user_id: uuid`, `before: dict`, `after: dict` | `users.py` | audit only |
| `users.UserDeactivated` | Account disabled. | `user_id: uuid`, `reason: Literal["admin_action"]` | `users.py` | audit only |
| `users.UserReactivated` | Re-enabled. | `user_id: uuid` | `users.py` | audit only |
| `users.PasswordResetByAdmin` | Admin force-reset a user's password. | `user_id: uuid`, `reset_by_user_id: uuid` | `users.py` | audit only |

## `platform.*` — settings, custom fields, form templates, notes, attachments, approvals

A grab-bag of platform-plumbing events. Subscribed only by audit unless
called out.

### Settings

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `settings.SettingChanged` | Owner set or changed a typed setting. | `key: str`, `old_value: Any`, `new_value: Any` | `services/settings/` | `settings_cache_invalidator`, audit |

Note: type string is `settings.SettingChanged` (not `platform.*`) — kept for
historical reasons; the aggregate is the settings module.

### Custom fields & form templates

Aggregate types: `custom_field`, `form_template`. Issue: Phase 2.5.

| Type | Description | Payload |
|---|---|---|
| `platform.CustomFieldCreated` | New field definition. | `custom_field_id: uuid`, `entity_type: str`, `key: str`, `label: str`, `field_type: str`, `required: bool` |
| `platform.CustomFieldUpdated` | Definition changed. | `custom_field_id: uuid`, `before: dict`, `after: dict` |
| `platform.CustomFieldArchived` | Soft-archive. | `custom_field_id: uuid` |
| `platform.CustomFieldUnarchived` | Restore. | `custom_field_id: uuid` |
| `platform.FormTemplateCreated` | New template. | `template_id: uuid`, `entity_type: str`, `name: str`, `is_default_for_entity_type: bool` |
| `platform.FormTemplateUpdated` | Template metadata changed. | `template_id: uuid`, `before: dict`, `after: dict` |
| `platform.FormTemplateDefaulted` | Set as default for an entity type. | `template_id: uuid`, `entity_type: str`, `previous_default_template_id: uuid | None` |
| `platform.FormTemplateArchived` | Soft-archive. | `template_id: uuid` |
| `platform.FormTemplateFieldAdded` | Bound a field into a template. | `template_id: uuid`, `custom_field_id: uuid`, `display_order: int` |
| `platform.FormTemplateFieldRemoved` | Unbound a field. | `template_id: uuid`, `custom_field_id: uuid` |

Emitted by `services/custom_fields.py` and `services/form_templates.py`.
Subscribed by audit only.

### Notes & attachments

Polymorphic `(entity_kind, entity_id)` refs. Note bodies never appear in
payloads in full — only a 100-char preview slice (see `body_preview()` in
`app/events/types/notes_attachments.py`). Issue: Phase 2.6.

| Type | Description | Payload |
|---|---|---|
| `platform.NoteCreated` | Note added on a host entity. | `note_id: uuid`, `entity_kind: str`, `entity_id: uuid`, `author_user_id: uuid`, `body_preview: str` |
| `platform.NoteUpdated` | Body edited. | `note_id: uuid`, `body_preview_before: str`, `body_preview_after: str` |
| `platform.NoteDeleted` | Note removed. | `note_id: uuid`, `entity_kind: str`, `entity_id: uuid` |
| `platform.NotePinned` | Pinned to the top. | `note_id: uuid` |
| `platform.NoteUnpinned` | Unpinned. | `note_id: uuid` |
| `platform.AttachmentUploaded` | File uploaded. Metadata only — no bytes, no storage path. | `attachment_id: uuid`, `entity_kind: str`, `entity_id: uuid`, `filename: str`, `mime_type: str`, `byte_size: int` |
| `platform.AttachmentArchived` | Soft-archive. | `attachment_id: uuid` |

Emitted by `services/notes.py` and `services/attachments/`. Subscribed by
audit only.

### Approvals (Phase 4.4, #67)

Aggregate type: `approval_request`. The full proposed mutation lives on
the `approval_request` row, **never** in the event payload — only a short
`payload_summary` does. Regression-tested.

| Type | Description | Payload |
|---|---|---|
| `platform.ApprovalRequested` | Workflow opened. | `request_id: uuid`, `request_type: str`, `subject_kind: str`, `subject_id: uuid`, `requested_by_user_id: uuid`, `payload_summary: str`, `threshold_amount: str | None` |
| `platform.ApprovalApproved` | Approver said yes. Self-approval guarded. | `request_id: uuid`, `approver_user_id: uuid`, `decision_note_preview: str | None` (first 100 chars) |
| `platform.ApprovalRejected` | Approver said no. | `request_id: uuid`, `approver_user_id: uuid`, `decision_note_preview: str | None` |
| `platform.ApprovalCancelled` | Requester (or admin) withdrew. | `request_id: uuid`, `cancelled_by_user_id: uuid` |

Emitted by `services/approvals.py`. Subscribed by audit only.

## `catalog.*` — materials, supplies, rates, products, BOM

Aggregate types vary: `material`, `supply`, `rate`, `product`. All
payloads use `extra="forbid"`. Decimals serialize as canonical strings.

### Materials (Phase 2.1, #37)

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `catalog.MaterialCreated` | New material in the catalog. | `material_id: uuid`, `name: str`, `brand: str | None`, `material_type: str`, `color: str | None` | `materials.py` | audit only |
| `catalog.MaterialUpdated` | Field-level update. | `material_id: uuid`, `before: dict`, `after: dict` | `materials.py` | `product_cost` (cost field changes trigger BOM rollup), audit |
| `catalog.MaterialArchived` | Soft-archive. | `material_id: uuid` | `materials.py` | audit only |
| `catalog.MaterialUnarchived` | Restore. | `material_id: uuid` | `materials.py` | audit only |

### Supplies (Phase 2.2, #38)

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `catalog.SupplyCreated` | New supply. | `supply_id: uuid`, `name: str`, `unit: str`, `unit_cost: str`, `vendor: str | None` | `supplies.py` | audit only |
| `catalog.SupplyUpdated` | Field-level update. | `supply_id: uuid`, `before: dict`, `after: dict` | `supplies.py` | `product_cost` (cost field changes trigger BOM rollup), audit |
| `catalog.SupplyArchived` | Soft-archive. | `supply_id: uuid` | `supplies.py` | audit only |
| `catalog.SupplyUnarchived` | Restore. | `supply_id: uuid` | `supplies.py` | audit only |

### Rates (Phase 2.2, #38)

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `catalog.RateCreated` | New rate. | `rate_id: uuid`, `name: str`, `kind: str`, `value: str`, `is_default_for_kind: bool` | `rates.py` | audit only |
| `catalog.RateUpdated` | Update. | `rate_id: uuid`, `before: dict`, `after: dict` | `rates.py` | audit only |
| `catalog.RateDefaulted` | Promoted to default for its kind. | `rate_id: uuid`, `kind: str`, `previous_default_rate_id: uuid | None` | `rates.py` | audit only |
| `catalog.RateArchived` | Soft-archive. | `rate_id: uuid` | `rates.py` | audit only |
| `catalog.RateUnarchived` | Restore. | `rate_id: uuid` | `rates.py` | audit only |

### Products (Phase 2.3)

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `catalog.ProductCreated` | New product. | `product_id: uuid`, `sku: str`, `name: str`, `unit_price: str`, `category: str | None` | `products.py` | audit only |
| `catalog.ProductUpdated` | Field-level update. | `product_id: uuid`, `before: dict`, `after: dict` | `products.py` | audit only |
| `catalog.ProductPriceChanged` | Dedicated price-change event. | `product_id: uuid`, `old_price: str`, `new_price: str` | `products.py` | audit only |
| `catalog.ProductArchived` | Soft-archive. | `product_id: uuid` | `products.py` | audit only |
| `catalog.ProductUnarchived` | Restore. | `product_id: uuid` | `products.py` | audit only |

### BOM (Phase 2.4)

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `catalog.BomComponentAdded` | Component bound into a parent product's BOM. | `bom_item_id: uuid`, `parent_product_id: uuid`, `component_kind: str`, `component_id: uuid`, `quantity: str` | `bom.py` | `product_cost`, audit |
| `catalog.BomComponentRemoved` | Unbound a component. | `bom_item_id: uuid`, `parent_product_id: uuid`, `component_kind: str`, `component_id: uuid` | `bom.py` | `product_cost`, audit |
| `catalog.BomComponentQuantityChanged` | Quantity changed in place. | `bom_item_id: uuid`, `parent_product_id: uuid`, `old_quantity: str`, `new_quantity: str` | `bom.py` | `product_cost`, audit |
| `catalog.ProductCostChanged` | `unit_cost_cached` was recomputed. **Emitted by the `product_cost` projection**, not by service code; the projection subscribes to its own event to propagate cost up the BOM tree. | `product_id: uuid`, `old_cost: str | None`, `new_cost: str | None` | `product_cost` projection | `product_cost` (recursive), audit |

## `inventory.*` — receipts, transactions, locations

### Material receipts (Phase 2.1, #37)

Aggregate type: `material` (one event per receipt; the projection
recomputes weighted-average cost and on-hand grams for the material).

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `inventory.MaterialReceived` | One receipt row recorded. | `material_id: uuid`, `grams: Decimal`, `total_cost: Decimal`, `unit_cost_at_receipt: Decimal`, `vendor: str | None`, `reference: str | None` | `material_receipts.py` | `material_cost`, `product_cost` (BOM rollup if cost moves), audit |

### Inventory locations (Phase 3.1, #50)

Aggregate type: `inventory_location`. Catalog-style CRUD.

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `inventory.LocationCreated` | New location. | `location_id: uuid`, `name: str`, `code: str`, `kind: str` | `inventory_locations.py` | audit only |
| `inventory.LocationUpdated` | Update. | `location_id: uuid`, `before: dict`, `after: dict` | `inventory_locations.py` | audit only |
| `inventory.LocationArchived` | Soft-archive. | `location_id: uuid` | `inventory_locations.py` | audit only |
| `inventory.LocationUnarchived` | Restore. | `location_id: uuid` | `inventory_locations.py` | audit only |

### Inventory transactions (Phase 3.2, #51)

Aggregate type: `inventory_transaction`. Append-only ledger; one event
per transaction row.

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `inventory.TransactionRecorded` | Signed-quantity movement of a material / supply / product at a location. | `transaction_id: uuid`, `kind: str`, `entity_kind: str`, `entity_id: uuid`, `location_id: uuid`, `signed_quantity: Decimal`, `unit_cost: Decimal | None`, `total_cost: Decimal | None`, `transfer_pair_id: uuid | None`, `linked_job_id: uuid | None`, `linked_sale_id: uuid | None`, `reason: str | None` | `inventory_transactions.py` | `inventory_on_hand`, audit |

## `accounting.*` — accounts, journal entries, periods, divisions, budgets

### Chart of accounts (Phase 4.1, #64)

Aggregate type: `account`.

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `accounting.AccountCreated` | New chart-of-accounts row. | `account_id: uuid`, `code: str`, `name: str`, `type: str`, `parent_account_id: uuid | None` | `accounts.py` | audit only |
| `accounting.AccountUpdated` | Update. | `account_id: uuid`, `before: dict`, `after: dict` | `accounts.py` | audit only |
| `accounting.AccountArchived` | Soft-archive. | `account_id: uuid` | `accounts.py` | audit only |
| `accounting.AccountUnarchived` | Restore. | `account_id: uuid` | `accounts.py` | audit only |

### Journal entries (Phase 4.2, #65)

Aggregate type: `journal_entry`. Lines do not have aggregate identity of
their own.

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `accounting.JournalEntryPosted` | Double-entry post. Service validates debits==credits. | `entry_id: uuid`, `entry_number: str`, `posted_at: str` (ISO8601 tz-aware), `period_id: uuid | None`, `description: str`, `source_event_id: uuid | None`, `actor_user_id: uuid | None`, `reversal_of_entry_id: uuid | None`, `lines: list[JournalLinePayload]` | `journal_entries.py` | `account_balance`, audit |
| `accounting.JournalEntryReversed` | Marker indicating a reversal entry exists. The reversal itself is a fresh `JournalEntryPosted`. | `original_entry_id: uuid`, `reversal_entry_id: uuid`, `reversal_entry_number: str` | `journal_entries.py` | `account_balance` (no-op; balance moves via the reversal's posting), audit |

`JournalLinePayload`: `account_id: uuid`, `debit: str` (Decimal), `credit:
str` (Decimal), `line_number: int`, `memo: str | None`, `division_id:
uuid | None` (Phase 4.5).

### Accounting periods (Phase 4.3, #66)

Aggregate type: `accounting_period`. State machine: `open → closed →
locked`, with `closed → open` reopen.

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `accounting.PeriodCreated` | New period (no overlap with existing). | `period_id: uuid`, `name: str`, `start_date: str`, `end_date: str` | `accounting_periods.py` | audit only |
| `accounting.PeriodUpdated` | Renamed or re-dated. | `period_id: uuid`, `before: dict`, `after: dict` | `accounting_periods.py` | audit only |
| `accounting.PeriodClosed` | Closed for posting. | `period_id: uuid`, `closed_by_user_id: uuid | None` | `accounting_periods.py` | audit only |
| `accounting.PeriodReopened` | Closed → open. | `period_id: uuid`, `reopened_by_user_id: uuid | None` | `accounting_periods.py` | audit only |
| `accounting.PeriodLocked` | Permanent lock (no reopen). | `period_id: uuid`, `locked_by_user_id: uuid | None` | `accounting_periods.py` | audit only |

### Divisions & budgets (Phase 4.5, #68)

Aggregate types: `division`, `budget`.

| Type | Description | Payload | Emitted by | Subscribed by |
|---|---|---|---|---|
| `accounting.DivisionCreated` | New division. | `division_id: uuid`, `name: str`, `code: str` | `divisions.py` | audit only |
| `accounting.DivisionUpdated` | Update. | `division_id: uuid`, `before: dict`, `after: dict` | `divisions.py` | audit only |
| `accounting.DivisionArchived` | Soft-archive. | `division_id: uuid` | `divisions.py` | audit only |
| `accounting.DivisionUnarchived` | Restore. | `division_id: uuid` | `divisions.py` | audit only |
| `accounting.BudgetSet` | Budget slot `(account, division?, period)` set or updated. | `account_id: uuid`, `division_id: uuid | None`, `period_id: uuid`, `old_amount: str | None`, `new_amount: str` | `budgets.py` | audit only |
| `accounting.BudgetUnset` | Slot cleared. | `account_id: uuid`, `division_id: uuid | None`, `period_id: uuid` | `budgets.py` | audit only |

## `test.*` — smoke-test event

| Type | Description |
|---|---|
| `test.TestEvent` | Smoke-test type used by the projection scaffolding. Payload: `value: str`. Subscribed by `test_event_projection` writing to `projection_test_event`. Do not use for business logic. |

## Audit excerpt whitelist

The audit projection (`app/projections/audit/`) writes one `audit_log`
row per event and **may** denormalize a tiny subset of the payload into
`audit_log.payload_excerpt`. Two rules govern that subset:

1. **Deny by default.** No excerpt unless the event type is explicitly
   registered via `register_excerpt_fields(event_type, fields)` in
   `app/projections/audit/excerpts.py`. Unknown types fall through to
   `payload_excerpt = NULL`.
2. **Sensitive fields never appear, even by accident.** A
   `_FORBIDDEN_FIELDS` frozenset (`password`, `password_hash`, `token`,
   `token_hash`, `refresh_token`, `access_token`, `session_id`, `secret`)
   is enforced at registration time (raises `ValueError`) and a second
   filter at write time. Belt-and-suspenders.

Per-event-type whitelists currently in force:

| Event | Whitelisted fields |
|---|---|
| `auth.LoginSucceeded` | `email` |
| `auth.LoginFailed` | `email` |
| `auth.LoginInactive` | `email` |
| `auth.RefreshRotated`, `auth.LoggedOut`, `auth.FamilyRevoked`, `auth.RateLimited` | — (no excerpt) |
| `users.UserCreated` | `email`, `full_name`, `role` |
| `users.UserUpdated` | `before`, `after` |
| `users.UserDeactivated` | `reason` |
| `users.UserReactivated`, `users.PasswordResetByAdmin` | — |
| `catalog.MaterialCreated` | `name`, `brand`, `material_type`, `color` |
| `catalog.MaterialUpdated` | `before`, `after` |
| `catalog.SupplyCreated` | `name`, `unit`, `unit_cost`, `vendor` |
| `catalog.SupplyUpdated` | `before`, `after` |
| `catalog.RateCreated` | `name`, `kind`, `value`, `is_default_for_kind` |
| `catalog.RateUpdated` | `before`, `after` |
| `catalog.RateDefaulted` | `kind`, `previous_default_rate_id` |
| `catalog.ProductCreated` | `sku`, `name`, `category` (`description` deliberately not whitelisted) |
| `catalog.ProductUpdated` | `before`, `after` |
| `catalog.ProductPriceChanged` | `old_price`, `new_price` |
| `catalog.BomComponentAdded` | `parent_product_id`, `component_kind`, `component_id`, `quantity` |
| `catalog.BomComponentRemoved` | `parent_product_id`, `component_kind`, `component_id` |
| `catalog.BomComponentQuantityChanged` | `parent_product_id`, `old_quantity`, `new_quantity` |
| `catalog.ProductCostChanged` | `product_id`, `old_cost`, `new_cost` |
| `inventory.MaterialReceived` | `material_id`, `grams`, `total_cost` (`notes` deliberately not whitelisted — could contain vendor account numbers) |
| `inventory.LocationCreated` | `name`, `code`, `kind` |
| `inventory.LocationUpdated` | `before`, `after` |
| `inventory.TransactionRecorded` | `kind`, `entity_kind`, `entity_id`, `location_id`, `signed_quantity`, `reason` (`unit_cost` / `total_cost` deliberately not whitelisted) |
| `platform.CustomFieldCreated` | `entity_type`, `key`, `label`, `field_type`, `required` |
| `platform.CustomFieldUpdated` | `before`, `after` |
| `platform.FormTemplateCreated` | `entity_type`, `name` |
| `platform.FormTemplateUpdated` | `before`, `after` |
| `platform.FormTemplateDefaulted` | `entity_type`, `previous_default_template_id` |
| `platform.FormTemplateFieldAdded` | `custom_field_id`, `display_order` |
| `platform.FormTemplateFieldRemoved` | `custom_field_id` |
| `platform.NoteCreated` | `entity_kind`, `entity_id`, `author_user_id`, `body_preview` |
| `platform.NoteUpdated` | `body_preview_before`, `body_preview_after` |
| `platform.NoteDeleted` | `entity_kind`, `entity_id` |
| `platform.AttachmentUploaded` | `entity_kind`, `entity_id`, `filename`, `mime_type`, `byte_size` (`storage_path` deliberately not in the event payload at all) |
| `accounting.AccountCreated` | `code`, `name`, `type`, `parent_account_id` |
| `accounting.AccountUpdated` | `before`, `after` |
| `accounting.JournalEntryPosted` | `entry_number`, `description`, `actor_user_id`, `posted_at`, `lines` (summarized via a transformer to `{count, total_debit, total_credit}` — the raw lines are not denormalized) |
| `accounting.JournalEntryReversed` | `original_entry_id`, `reversal_entry_id`, `reversal_entry_number` |
| `accounting.PeriodCreated` | `name`, `start_date`, `end_date` |
| `accounting.PeriodUpdated` | `before`, `after` |
| `accounting.PeriodClosed` | `closed_by_user_id` |
| `accounting.PeriodReopened` | `reopened_by_user_id` |
| `accounting.PeriodLocked` | `locked_by_user_id` |
| `platform.ApprovalRequested` | `request_type`, `subject_kind`, `subject_id`, `requested_by_user_id`, `threshold_amount`, `payload_summary` (the **full** `payload` is intentionally NOT whitelisted — guarded by `test_approvals_payload_not_leaked_to_audit.py`) |
| `platform.ApprovalApproved` | `approver_user_id`, `decision_note_preview` |
| `platform.ApprovalRejected` | `approver_user_id`, `decision_note_preview` |
| `platform.ApprovalCancelled` | `cancelled_by_user_id` |
| `accounting.DivisionCreated` | `name`, `code` |
| `accounting.DivisionUpdated` | `before`, `after` |
| `accounting.BudgetSet` | `account_id`, `division_id`, `period_id`, `old_amount`, `new_amount` |
| `accounting.BudgetUnset` | `account_id`, `division_id`, `period_id` |

Anything not in the table above writes `audit_log.payload_excerpt = NULL`.
The `settings.SettingChanged` event has no whitelist registered — values
are intentionally kept out of the audit log because some settings (e.g.
storage roots, future API keys) could be operationally sensitive.
