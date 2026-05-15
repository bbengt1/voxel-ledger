# Migration changelog

Reverse-chronological index of every Alembic revision in
`backend/alembic/versions/`. Newest first — the most-recent deploy's
schema delta is at the top.

For the cross-cutting rules every migration must honor (boolean defaults,
ENUM declaration pattern, `sa.false()`, dialect-portability), see the
[Migration hygiene](#migration-hygiene) section at the bottom and
[`../agents.md`](../agents.md).

Cross-references:
[`architecture.md`](architecture.md) for what the schema serves,
[`event_catalog.md`](event_catalog.md) for which events drive the
projections that populate the read-model tables.

---

### `0021_divisions_budgets` — `0021_divisions_budgets.py` (Phase 4.5, #68)

Adds the `division` aggregate and the `budget` slot table; adds an
optional `journal_line.division_id` for the second analytical
dimension.

- Creates `division` (id, name, code, is_archived, timestamps), with a
  partial unique index on `code WHERE is_archived = false`.
- Creates `budget` keyed on `(account_id, division_id, period_id)`.
  **Dialect-aware uniqueness:** on PG 15+ the constraint is emitted via
  raw SQL as `UNIQUE (..., NULLS NOT DISTINCT)` so a NULL `division_id`
  (the catch-all budget) is genuinely unique; on SQLite the plain
  `UNIQUE` is added and `BudgetsService.set` carries the upsert logic.
- Adds nullable `journal_line.division_id` with FK to `division(id)`.
- Boolean defaults via `sa.false()`. No new enums.

### `0020_approvals` — `0020_approvals.py` (Phase 4.4, #67)

Adds the generic approval-queue table.

- Creates `approval_request` (id, request_type, subject_kind,
  subject_id, requested_by_user_id, state, payload, decision_note,
  threshold_amount, timestamps, approver_user_id, etc.).
- Creates ENUM `approval_state` via the column declaration
  (`sa.Enum(*VALUES, name="approval_state")` — not pre-created).
- `payload` is JSONB on PG, JSON on SQLite.
- Four supporting indexes for the queue read paths.

### `0019_accounting_periods` — `0019_accounting_periods.py` (Phase 4.3, #66)

Adds the accounting-period aggregate with state machine and overlap
protection. Tightens `journal_entry.period_id` to `NOT NULL` after
backfill.

- Installs the `btree_gist` extension on PG (idempotent).
- Creates ENUM `accounting_period_state` (`open / closed / locked`) via
  the column declaration.
- Creates `accounting_period` with the state column, lock metadata, and
  (on PG only) a GiST exclusion constraint over `daterange(start_date,
  end_date, '[]')` so overlapping periods are rejected at the DB level.
  The service-layer overlap check is the primary defense; this is the
  safety net.
- Three supporting indexes.
- **Data migration:** any existing `journal_entry` rows with
  `period_id IS NULL` are matched to a freshly-created period by
  `posted_at`. On a fresh dev DB this is a no-op (no rows yet). If rows
  exist and no period covers them, the migration aborts with a clear
  error — the operator must create covering periods first.
- After backfill: alters `journal_entry.period_id` to `NOT NULL` and
  re-asserts the FK.

### `0018_journal_entries` — `0018_journal_entries.py` (Phase 4.2, #65)

The double-entry guts. Adds the journal tables and the running-balance
read model.

- Creates `journal_entry` (id, entry_number, posted_at, period_id
  nullable for now — see #0019, description, source_event_id, actor,
  reversal_of_entry_id, is_reversed, timestamps).
- Creates `journal_line` (id, journal_entry_id, account_id, debit,
  credit, line_number, memo) with FKs.
- Creates `account_balance` (account_id PK, balance) — the projection
  table for `account_balance` projection.
- On PG only: `BEFORE UPDATE OR DELETE` immutability triggers on both
  `journal_entry` and `journal_line`. The `journal_entry` trigger has a
  narrow carve-out allowing `is_reversed` to flip from `false → true`
  with every other column unchanged.
- Boolean defaults via `sa.false()`. No new enums.

### `0017_accounts` — `0017_accounts.py` (Phase 4.1, #64)

Chart of accounts.

- Creates `account` (id, code, name, type, parent_account_id self-FK,
  is_archived, timestamps).
- Creates ENUM `account_type` via the column declaration.
- Partial unique index on `code WHERE is_archived = false`.
- Support indexes on `(parent_account_id)` and `(type, code)`.
- Boolean defaults via `sa.false()`.

### `0016_inventory_on_hand_alerts` — `0016_inventory_on_hand_alerts.py` (Phase 3.3, #52)

**Operator-facing gotcha — read this one before deploying.** This is the
migration that breaks if you don't read the docs.

- Creates `inventory_on_hand` per-`(entity_kind, entity_id, location_id)`
  running balance, owned by the `inventory_on_hand` projection.
- Adds `low_stock_threshold` (and friends) to `material`, `supply`, and
  `product`.
- **Data migration: backfills existing on-hand quantities from
  `material.on_hand_grams` and `supply.on_hand` into the new
  `inventory_on_hand` table.** For each row with a positive on-hand
  quantity, the destination location is:
  1. The `inventory.default_receiving_location_id` setting, if set.
  2. Otherwise, the lowest-code active `workshop` location.
  3. Otherwise, **the migration fails**. The operator must configure a
     destination before upgrading.
- **Drops `material.on_hand_grams` and `supply.on_hand`** after the
  backfill succeeds.
- Downgrade re-adds the dropped columns as nullable `Numeric(18,6)`,
  **empty** — on-hand state does not survive a downgrade. Snapshot the
  database first if you need to roll back.

### `0015_inventory_transactions` — `0015_inventory_transactions.py` (Phase 3.2, #51)

The append-only inventory ledger.

- Creates `inventory_transaction` (id, kind, entity_kind, entity_id,
  location_id, signed_quantity, unit_cost, total_cost, transfer_pair_id,
  linked_job_id, linked_sale_id, reason, actor_user_id, occurred_at).
- Creates ENUMs `inventory_transaction_kind` and `inventory_entity_kind`
  via column declarations.
- Composite indexes for the hot read paths: `(entity_kind, entity_id,
  occurred_at)`, `(location_id, occurred_at)`, etc.
- On PG only: `BEFORE UPDATE OR DELETE` immutability trigger.
- Boolean defaults via `sa.false()`.

### `0014_inventory_locations` — `0014_inventory_locations.py` (Phase 3.1, #50)

- Creates `inventory_location` (id, name, code, kind, is_archived,
  timestamps).
- Creates ENUM `inventory_location_kind` via the column declaration.
- Partial unique index on `code WHERE is_archived = false`.

### `0013_notes_attachments` — `0013_notes_attachments.py` (Phase 2.6)

- Creates `note` and `attachment` tables with polymorphic
  `(entity_kind, entity_id)` refs. No FK on `entity_id` — same pattern
  as `product_bom_item.component_id`.
- JSONB on PG, JSON on SQLite.
- **Data step:** inserts a default row for the `attachments.storage_root`
  setting if one does not already exist.

### `0012_custom_fields` — `0012_custom_fields.py` (Phase 2.5)

- Creates `custom_field`, `form_template`, and `form_template_field`
  tables.
- Creates ENUM `custom_field_type` via the column declaration.
- Adds a `custom_fields jsonb NOT NULL DEFAULT '{}'` column on each of
  `material`, `supply`, `rate`, `product`.

### `0011_product_bom` — `0011_product_bom.py` (Phase 2.4)

- Creates `product_bom_item` (id, parent_product_id, component_kind,
  component_id, quantity, timestamps).
- Creates ENUM `bom_component_kind` via the column declaration
  (`material / supply / product`).
- `component_id` is **not** an FK — polymorphic. Integrity is enforced
  in `app/services/bom.py`.

### `0010_products` — `0010_products.py` (Phase 2.3)

- Creates `product` (id, sku, name, unit_price, category, description,
  upc, unit_cost_cached nullable — populated later by the
  `product_cost` projection, custom_fields stub, is_archived,
  timestamps).
- Partial unique index on `upc WHERE upc IS NOT NULL` so multiple NULL
  UPCs may coexist.

### `0009_supplies_rates` — `0009_supplies_rates.py` (Phase 2.2, #38)

- Creates `supply` (unit-cost consumable; `on_hand` cache column added
  here, dropped in 0016).
- Creates `rate` (typed labor / machine / overhead).
- Creates ENUM `rate_kind` via the column declaration.
- Partial unique indexes: supply `(name, vendor) WHERE is_archived =
  false`, rate `(kind) WHERE is_default_for_kind = true` (so the
  default-rate "flip" is backstopped at the DB level).

### `0008_materials` — `0008_materials.py` (Phase 2.1, #37)

- Creates `material` (id, name, brand, material_type, color,
  current_cost_per_gram, on_hand_grams — both read-side caches owned by
  `material_cost` projection; on_hand_grams dropped in 0016).
- Creates `material_receipt` (the sub-resource feeding the weighted-
  average rollup).
- Partial unique index on `(name, brand, color) WHERE is_archived =
  false`.

### `0007_settings` — `0007_settings.py` (Phase 1.5)

- Creates `setting` (key PK, value JSONB, updated_at, updated_by).
- This is the runtime-editable typed key/value store — distinct from
  the env-driven `Settings` object read once at boot.

### `0006_audit_log` — `0006_audit_log.py` (Phase 1.4, #24)

- Creates `audit_log` (id, event_id, event_position UNIQUE, event_type,
  actor_user_id / actor_email / actor_role denormalized,
  aggregate_type, aggregate_id, occurred_at, summary, ip_address INET
  on PG, payload_excerpt JSONB) — the read model populated by the
  wildcard audit projection.

### `0005_reference_sequence` — `0005_reference_sequence.py` (Phase 1.3)

- Creates `reference_sequence (prefix, year, last_value)` with a
  composite PK. Backs the race-safe `{PREFIX}-{YYYY}-{NNNN}` allocator.
- (Was rebased onto 0004 at merge time — see the comment in the
  revision file. The graph stays linear.)

### `0004_projection_cursor` — `0004_projection_cursor.py` (Phase 1.2, #22)

- Creates `projection_cursor (handler_name PK, last_position)` — used
  only during out-of-band replay, never touched on the live path.
- Creates `projection_test_event` — the test-only read-model table fed
  by `app/projections/test_event_projection.py` so the projection
  scaffolding has something real to exercise.

### `0003_event_log` — `0003_event_log.py` (Phase 1.1)

The event log itself.

- Creates `event` (position BIGSERIAL PK, id UUID, type, aggregate_type,
  aggregate_id, payload JSONB, payload_hash, prev_hash, schema_version,
  actor_user_id, occurred_at, ip).
- On PG only: a `BEFORE UPDATE OR DELETE` trigger
  (`event_log_block_mutation_trg`) that rejects every mutation —
  append-only enforcement at the DB. SQLite skips the trigger and the
  invariant is exercised by a PG integration test.
- Supporting indexes on `(type, occurred_at)`, `(aggregate_type,
  aggregate_id, position)`, `(actor_user_id, occurred_at)`.

### `0002_auth` — `0002_auth.py` (Phase 0.7)

- Creates `user` (id, email UNIQUE, password_hash, full_name, role, is_active, timestamps).
- Creates `refresh_token` (id, user_id, family_id, parent_id self-FK,
  token_hash, expires_at, revoked_at, created_at).
- Creates ENUM `role` (`owner / bookkeeper / production / sales /
  viewer`) on PG; on SQLite the same construct becomes a CHECK.

### `0001_baseline` — `0001_baseline.py`

Empty baseline. No-op upgrade and downgrade. Every subsequent revision
chains off this.

---

## Migration hygiene

Two recurring gotchas this codebase has paid for. The full rule set
lives in [`../agents.md`](../agents.md); operator-relevant restatement:

**Boolean defaults must use `sa.false()` / `sa.true()`.** Postgres
rejects integer literals (`0` / `1`) as server defaults on Boolean
columns and the migration will fail mid-upgrade. SQLAlchemy renders
`sa.false()` correctly on both PG and SQLite, so this is the only safe
spelling. Every Boolean column in the codebase uses it; new migrations
must too.

**PG ENUM types are created via the column declaration, never pre-created.**
The pattern is `sa.Enum(*VALUES, name="my_enum")` referenced on the
column inside `op.create_table`. The dialect hook creates the type on
PG and renders `VARCHAR + CHECK` on SQLite. Pre-creating with
`postgresql.ENUM(...).create(bind)` worked in v1 but breaks
round-tripping on SQLite-backed tests and fights `op.create_table` on
PG; don't do it. Downgrades that drop a table that uses an ENUM should
also drop the enum type explicitly (see e.g. the `accounting_period_state`
drop in `0019`).
