# API Endpoints — Per Tag

Auto-generated from OpenAPI (373 operations across 46 tags).

## Tags

- [Accounting](#tag-accounting) — 29 endpoint(s)
- [AccountingFoundations](#tag-accountingfoundations) — 11 endpoint(s)
- [Approvals](#tag-approvals) — 3 endpoint(s)
- [Attachments](#tag-attachments) — 5 endpoint(s)
- [Audit](#tag-audit) — 1 endpoint(s)
- [Authentication](#tag-authentication) — 8 endpoint(s)
- [Banking](#tag-banking) — 30 endpoint(s)
- [BatchOperations](#tag-batchoperations) — 6 endpoint(s)
- [BillableExpenses](#tag-billableexpenses) — 5 endpoint(s)
- [Budgets](#tag-budgets) — 4 endpoint(s)
- [COGS](#tag-cogs) — 3 endpoint(s)
- [Cameras](#tag-cameras) — 8 endpoint(s)
- [CreditDebitNotes](#tag-creditdebitnotes) — 13 endpoint(s)
- [CustomFields](#tag-customfields) — 8 endpoint(s)
- [Customers](#tag-customers) — 5 endpoint(s)
- [Dashboard](#tag-dashboard) — 5 endpoint(s)
- [DeliveryNotes](#tag-deliverynotes) — 5 endpoint(s)
- [DivisionsProjects](#tag-divisionsprojects) — 8 endpoint(s)
- [Email](#tag-email) — 4 endpoint(s)
- [ExpenseClaims](#tag-expenseclaims) — 9 endpoint(s)
- [FixedAssets](#tag-fixedassets) — 9 endpoint(s)
- [FormTemplates](#tag-formtemplates) — 4 endpoint(s)
- [Health](#tag-health) — 1 endpoint(s)
- [Insights](#tag-insights) — 2 endpoint(s)
- [IntangibleAssets](#tag-intangibleassets) — 7 endpoint(s)
- [Inventory](#tag-inventory) — 21 endpoint(s)
- [Invoices](#tag-invoices) — 12 endpoint(s)
- [JobDiscovery](#tag-jobdiscovery) — 8 endpoint(s)
- [Jobs](#tag-jobs) — 8 endpoint(s)
- [Kits](#tag-kits) — 4 endpoint(s)
- [Materials](#tag-materials) — 8 endpoint(s)
- [Merge](#tag-merge) — 1 endpoint(s)
- [Orders](#tag-orders) — 12 endpoint(s)
- [Printers](#tag-printers) — 8 endpoint(s)
- [ProductionOrders](#tag-productionorders) — 6 endpoint(s)
- [Products](#tag-products) — 10 endpoint(s)
- [Quotes](#tag-quotes) — 6 endpoint(s)
- [Rates](#tag-rates) — 5 endpoint(s)
- [RecurringInvoices](#tag-recurringinvoices) — 9 endpoint(s)
- [Reports](#tag-reports) — 21 endpoint(s)
- [Sales](#tag-sales) — 16 endpoint(s)
- [Settings](#tag-settings) — 4 endpoint(s)
- [Settlements](#tag-settlements) — 3 endpoint(s)
- [Supplies](#tag-supplies) — 6 endpoint(s)
- [Tax](#tag-tax) — 8 endpoint(s)
- [Withholding](#tag-withholding) — 4 endpoint(s)

---

## Tag: Accounting <a id="tag-accounting"></a>

### `GET /api/v1/accounting/accounts` — List chart of accounts (admin only)

_operationId:_ `list_accounts_api_v1_accounting_accounts_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  |  |
| `account_type` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`AccountResponse`](#schema-accountresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/accounts` — Create account (admin only)

_operationId:_ `create_account_api_v1_accounting_accounts_post`

**Request body**
- `application/json` → [`AccountCreate`](#schema-accountcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`AccountResponse`](#schema-accountresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/accounting/accounts/{account_id}` — Update account (admin only)

_operationId:_ `update_account_api_v1_accounting_accounts__account_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `account_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`AccountUpdate`](#schema-accountupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`AccountResponse`](#schema-accountresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/accounting/bills` — List bills/expenses (admin only)

_operationId:_ `list_bills_api_v1_accounting_bills_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BillResponse`](#schema-billresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/bills` — Create bill/expense (admin only)

_operationId:_ `create_bill_api_v1_accounting_bills_post`

**Request body**
- `application/json` → [`BillCreate`](#schema-billcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`BillResponse`](#schema-billresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/accounting/bills/{bill_id}` — Update bill/expense (admin only)

_operationId:_ `update_bill_api_v1_accounting_bills__bill_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `bill_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`BillUpdate`](#schema-billupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BillResponse`](#schema-billresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/bills/{bill_id}/payments` — Record bill payment (admin only)

_operationId:_ `create_bill_payment_api_v1_accounting_bills__bill_id__payments_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `bill_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`BillPaymentCreate`](#schema-billpaymentcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`BillPaymentResponse`](#schema-billpaymentresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/accounting/expense-categories` — List expense categories (admin only)

_operationId:_ `list_expense_categories_api_v1_accounting_expense_categories_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ExpenseCategoryResponse`](#schema-expensecategoryresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/expense-categories` — Create expense category (admin only)

_operationId:_ `create_expense_category_api_v1_accounting_expense_categories_post`

**Request body**
- `application/json` → [`ExpenseCategoryCreate`](#schema-expensecategorycreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`ExpenseCategoryResponse`](#schema-expensecategoryresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/accounting/expense-categories/{category_id}` — Update expense category (admin only)

_operationId:_ `update_expense_category_api_v1_accounting_expense_categories__category_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `category_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ExpenseCategoryUpdate`](#schema-expensecategoryupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ExpenseCategoryResponse`](#schema-expensecategoryresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/accounting/journal-entries` — List journal entries (admin only)

_operationId:_ `list_entries_api_v1_accounting_journal_entries_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status` | query | string \| null |  |  |
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`JournalEntryResponse`](#schema-journalentryresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/journal-entries` — Create and post a journal entry (admin only)

_operationId:_ `create_entry_api_v1_accounting_journal_entries_post`

**Request body**
- `application/json` → [`JournalEntryCreate`](#schema-journalentrycreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`JournalEntryResponse`](#schema-journalentryresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/accounting/journal-entries/{entry_id}` — Get journal entry by ID (admin only)

_operationId:_ `get_entry_api_v1_accounting_journal_entries__entry_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `entry_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`JournalEntryResponse`](#schema-journalentryresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/journal-entries/{entry_id}/reverse` — Reverse a posted journal entry (admin only)

_operationId:_ `reverse_entry_api_v1_accounting_journal_entries__entry_id__reverse_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `entry_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`JournalEntryReverse`](#schema-journalentryreverse)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`JournalEntryResponse`](#schema-journalentryresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/accounting/period-close-date` — Get the configured period-close date (admin only)

_operationId:_ `get_period_close_date_endpoint_api_v1_accounting_period_close_date_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PeriodCloseDateResponse`](#schema-periodclosedateresponse) | Successful Response |

### `PUT /api/v1/accounting/period-close-date` — Set or clear the period-close date (admin only)

_operationId:_ `set_period_close_date_endpoint_api_v1_accounting_period_close_date_put`

**Request body**
- `application/json` → [`PeriodCloseDateUpdate`](#schema-periodclosedateupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PeriodCloseDateResponse`](#schema-periodclosedateresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/accounting/periods` — List accounting periods (admin only)

_operationId:_ `list_periods_api_v1_accounting_periods_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`AccountingPeriodResponse`](#schema-accountingperiodresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/periods` — Create accounting period (admin only)

_operationId:_ `create_period_api_v1_accounting_periods_post`

**Request body**
- `application/json` → [`AccountingPeriodCreate`](#schema-accountingperiodcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`AccountingPeriodResponse`](#schema-accountingperiodresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/accounting/periods/{period_id}` — Update accounting period (admin only)

_operationId:_ `update_period_api_v1_accounting_periods__period_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `period_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`AccountingPeriodUpdate`](#schema-accountingperiodupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`AccountingPeriodResponse`](#schema-accountingperiodresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/periods/{period_id}/status` — Change accounting period status (admin only)

_operationId:_ `change_period_status_api_v1_accounting_periods__period_id__status_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `period_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`AccountingPeriodStatusUpdate`](#schema-accountingperiodstatusupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`AccountingPeriodResponse`](#schema-accountingperiodresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/accounting/recurring-expenses` — List recurring expense templates (admin only)

_operationId:_ `list_recurring_expenses_api_v1_accounting_recurring_expenses_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RecurringExpenseResponse`](#schema-recurringexpenseresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/recurring-expenses` — Create recurring expense template (admin only)

_operationId:_ `create_recurring_expense_api_v1_accounting_recurring_expenses_post`

**Request body**
- `application/json` → [`RecurringExpenseCreate`](#schema-recurringexpensecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`RecurringExpenseResponse`](#schema-recurringexpenseresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/accounting/recurring-expenses/{recurring_id}` — Update recurring expense template (admin only)

_operationId:_ `update_recurring_expense_api_v1_accounting_recurring_expenses__recurring_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `recurring_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`RecurringExpenseUpdate`](#schema-recurringexpenseupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RecurringExpenseResponse`](#schema-recurringexpenseresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/recurring-expenses/{recurring_id}/generate` — Generate bill from recurring expense template (admin only)

_operationId:_ `generate_recurring_bill_api_v1_accounting_recurring_expenses__recurring_id__generate_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `recurring_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`RecurringExpenseGenerate`](#schema-recurringexpensegenerate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`BillResponse`](#schema-billresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/accounting/reports/expenses/by-category` — Expense summary by category (admin only)

_operationId:_ `expense_summary_by_category_api_v1_accounting_reports_expenses_by_category_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ExpenseSummaryRow`](#schema-expensesummaryrow)[] | Successful Response |

### `GET /api/v1/accounting/reports/expenses/by-vendor` — Expense summary by vendor (admin only)

_operationId:_ `expense_summary_by_vendor_api_v1_accounting_reports_expenses_by_vendor_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ExpenseSummaryRow`](#schema-expensesummaryrow)[] | Successful Response |

### `GET /api/v1/accounting/vendors` — List vendors (admin only)

_operationId:_ `list_vendors_api_v1_accounting_vendors_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`VendorResponse`](#schema-vendorresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/vendors` — Create vendor (admin only)

_operationId:_ `create_vendor_api_v1_accounting_vendors_post`

**Request body**
- `application/json` → [`VendorCreate`](#schema-vendorcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`VendorResponse`](#schema-vendorresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/accounting/vendors/{vendor_id}` — Update vendor (admin only)

_operationId:_ `update_vendor_api_v1_accounting_vendors__vendor_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `vendor_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`VendorUpdate`](#schema-vendorupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`VendorResponse`](#schema-vendorresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: AccountingFoundations <a id="tag-accountingfoundations"></a>

### `GET /api/v1/accounting/recurring-journal-entries` — List recurring JEs

_operationId:_ `list_rjes_api_v1_accounting_recurring_journal_entries_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RJEResponse`](#schema-rjeresponse)[] | Successful Response |

### `POST /api/v1/accounting/recurring-journal-entries` — Create a recurring JE

_operationId:_ `create_rje_api_v1_accounting_recurring_journal_entries_post`

**Request body**
- `application/json` → [`RJECreate`](#schema-rjecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`RJEResponse`](#schema-rjeresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/recurring-journal-entries/run-due` — Cron entry point

_operationId:_ `run_due_rje_api_v1_accounting_recurring_journal_entries_run_due_post`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |

### `PATCH /api/v1/accounting/recurring-journal-entries/{rje_id}` — Update recurring JE

_operationId:_ `update_rje_api_v1_accounting_recurring_journal_entries__rje_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `rje_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`RJEUpdate`](#schema-rjeupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RJEResponse`](#schema-rjeresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/accounting/recurring-journal-entries/{rje_id}` — Delete recurring JE

_operationId:_ `delete_rje_api_v1_accounting_recurring_journal_entries__rje_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `rje_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/recurring-journal-entries/{rje_id}/run-now` — Generate one JE now

_operationId:_ `run_now_rje_api_v1_accounting_recurring_journal_entries__rje_id__run_now_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `rje_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__accounting_foundations__RunResponse`](#schema-app__api__v1__endpoints__accounting_foundations__runresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/recurring-journal-entries/{rje_id}/skip-next` — Skip next run

_operationId:_ `skip_next_rje_api_v1_accounting_recurring_journal_entries__rje_id__skip_next_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `rje_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__accounting_foundations__RunResponse`](#schema-app__api__v1__endpoints__accounting_foundations__runresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/starting-balances` — Admin one-shot: post opening balances JE balanced against OBE (3300)

_operationId:_ `post_starting_balances_ep_api_v1_accounting_starting_balances_post`

**Request body**
- `application/json` → [`StartingBalancesRequest`](#schema-startingbalancesrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/accounting/starting-balances.csv` — #330 P2: Post opening balances from a CSV (account_code,amount[,as_of])

_operationId:_ `post_starting_balances_csv_api_v1_accounting_starting_balances_csv_post`

Accepts a CSV with header row `account_code,amount` (and optional
`as_of` column to override the request param). Resolves account codes to
IDs server-side, then forwards to the same posting service as the JSON
endpoint, so the JE shape matches.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `as_of` | query | string(date) \| null |  |  |
| `force` | query | boolean |  |  |

**Request body**
- `multipart/form-data` → [`Body_post_starting_balances_csv_api_v1_accounting_starting_balances_csv_post`](#schema-body_post_starting_balances_csv_api_v1_accounting_starting_balances_csv_post)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/accounting/suspense` — List open Suspense (1900) journal lines for reclassification

_operationId:_ `get_suspense_api_v1_accounting_suspense_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |

### `POST /api/v1/accounting/suspense/reclassify` — #330 P2: Reclassify a Suspense (1900) line by posting an offsetting JE

_operationId:_ `reclassify_suspense_line_api_v1_accounting_suspense_reclassify_post`

Closes out a Suspense line by posting a balanced JE: offset the
suspense leg and post the same amount to the chosen target account.
Original line stays put for audit; this is additive.

**Request body**
- `application/json` → [`SuspenseReclassifyRequest`](#schema-suspensereclassifyrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Approvals <a id="tag-approvals"></a>

### `GET /api/v1/approvals` — List approval requests (admin only)

_operationId:_ `list_approvals_api_v1_approvals_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ApprovalRequestResponse`](#schema-approvalrequestresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/approvals/{approval_id}/approve` — Approve request (admin only)

_operationId:_ `approve_request_api_v1_approvals__approval_id__approve_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `approval_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ApprovalDecisionBody`](#schema-approvaldecisionbody)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ApprovalRequestResponse`](#schema-approvalrequestresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/approvals/{approval_id}/reject` — Reject request (admin only)

_operationId:_ `reject_request_api_v1_approvals__approval_id__reject_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `approval_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ApprovalDecisionBody`](#schema-approvaldecisionbody)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ApprovalRequestResponse`](#schema-approvalrequestresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Attachments <a id="tag-attachments"></a>

### `DELETE /api/v1/attachments/{attachment_id}` — Soft-delete an attachment

_operationId:_ `delete_api_v1_attachments__attachment_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `attachment_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/attachments/{attachment_id}/download` — Download an attachment's bytes (server-proxied)

_operationId:_ `download_api_v1_attachments__attachment_id__download_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `attachment_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/attachments/{attachment_id}/thumbnail` — Download attachment thumbnail (404 if non-image)

_operationId:_ `thumbnail_api_v1_attachments__attachment_id__thumbnail_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `attachment_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/attachments/{scope}/{record_id}` — List attachments for a scoped record

_operationId:_ `list_for_record_api_v1_attachments__scope___record_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |
| `record_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`AttachmentResponse`](#schema-attachmentresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/attachments/{scope}/{record_id}` — Upload an attachment for a scoped record

_operationId:_ `upload_api_v1_attachments__scope___record_id__post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |
| `record_id` | path | string(uuid) | ✓ |  |

**Request body**
- `multipart/form-data` → [`Body_upload_api_v1_attachments__scope___record_id__post`](#schema-body_upload_api_v1_attachments__scope___record_id__post)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`AttachmentResponse`](#schema-attachmentresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Audit <a id="tag-audit"></a>

### `GET /api/v1/audit/logs` — List audit logs (admin only)

_operationId:_ `list_audit_logs_api_v1_audit_logs_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `entity_type` | query | string \| null |  |  |
| `entity_id` | query | string \| null |  |  |
| `action` | query | string \| null |  |  |
| `limit` | query | integer |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`AuditLogResponse`](#schema-auditlogresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Authentication <a id="tag-authentication"></a>

### `POST /api/v1/auth/login` — Authenticate user

_operationId:_ `login_api_v1_auth_login_post`

Validates email and password, returns a JWT access token.

**Request body**
- `application/json` → [`LoginRequest`](#schema-loginrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`TokenResponse`](#schema-tokenresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/auth/me` — Get current user

_operationId:_ `get_me_api_v1_auth_me_get`

Returns the profile of the currently authenticated user.

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`UserResponse`](#schema-userresponse) | Successful Response |

### `PUT /api/v1/auth/me/password` — Change password

_operationId:_ `change_password_api_v1_auth_me_password_put`

Change the current user's password. Requires the current password for verification.

**Request body**
- `application/json` → [`PasswordChange`](#schema-passwordchange)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`UserResponse`](#schema-userresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/auth/register` — Register a new user (admin only)

_operationId:_ `register_api_v1_auth_register_post`

Create a new user account. Only administrators can create accounts.

**Request body**
- `application/json` → [`UserCreate`](#schema-usercreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`UserResponse`](#schema-userresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/auth/users` — List users (admin only)

_operationId:_ `list_users_api_v1_auth_users_get`

Returns all user accounts. Only administrators can view the user list.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  | Filter by active status |
| `skip` | query | integer |  |  |
| `limit` | query | integer |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`UserResponse`](#schema-userresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/auth/users/{user_id}` — Get user by ID (admin only)

_operationId:_ `get_user_api_v1_auth_users__user_id__get`

Retrieve a single user account.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `user_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`UserResponse`](#schema-userresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/auth/users/{user_id}` — Update user (admin only)

_operationId:_ `update_user_api_v1_auth_users__user_id__put`

Update a user's profile, role, or active status. Admins cannot deactivate themselves.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `user_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`UserUpdate`](#schema-userupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`UserResponse`](#schema-userresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/auth/users/{user_id}` — Deactivate user (admin only)

_operationId:_ `deactivate_user_api_v1_auth_users__user_id__delete`

Soft-deletes a user by setting is_active=false. Admins cannot deactivate themselves.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `user_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Banking <a id="tag-banking"></a>

### `GET /api/v1/banking/accounts` — List bank-typed accounts with running balance

_operationId:_ `list_bank_accounts_api_v1_banking_accounts_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BankAccountResponse`](#schema-bankaccountresponse)[] | Successful Response |

### `PATCH /api/v1/banking/accounts/{account_id}/flag` — Flag or unflag a GL account as a bank account

_operationId:_ `flag_bank_account_api_v1_banking_accounts__account_id__flag_patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `account_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`BankAccountFlagRequest`](#schema-bankaccountflagrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BankAccountResponse`](#schema-bankaccountresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/imports` — List statement imports

_operationId:_ `list_imports_api_v1_banking_imports_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `account_id` | query | string(uuid) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`StatementImportResponse`](#schema-statementimportresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/banking/imports` — Upload a statement file (OFX or CSV)

_operationId:_ `upload_import_api_v1_banking_imports_post`

**Request body**
- `multipart/form-data` → [`Body_upload_import_api_v1_banking_imports_post`](#schema-body_upload_import_api_v1_banking_imports_post)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`StatementImportResponse`](#schema-statementimportresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/imports/accounts/{account_id}/csv-mapping` — #315 P2: Get persisted CSV column mapping for a bank account

_operationId:_ `get_mapping_api_v1_banking_imports_accounts__account_id__csv_mapping_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `account_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`MappingResponse`](#schema-mappingresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/banking/imports/accounts/{account_id}/csv-mapping` — #315 P2: Set the CSV column mapping for a bank account

_operationId:_ `set_mapping_api_v1_banking_imports_accounts__account_id__csv_mapping_put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `account_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`MappingUpsertRequest`](#schema-mappingupsertrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`MappingResponse`](#schema-mappingresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/banking/imports/accounts/{account_id}/csv-mapping` — #315 P2: Clear the CSV column mapping for a bank account

_operationId:_ `delete_mapping_api_v1_banking_imports_accounts__account_id__csv_mapping_delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `account_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/banking/imports/lines/{statement_line_id}/create-transaction` — #315 P2: Post a JE to clear an unmatched statement line

_operationId:_ `create_tx_ep_api_v1_banking_imports_lines__statement_line_id__create_transaction_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `statement_line_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`CreateTxRequest`](#schema-createtxrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/banking/imports/lines/{statement_line_id}/ignore` — Ignore a statement line

_operationId:_ `ignore_ep_api_v1_banking_imports_lines__statement_line_id__ignore_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `statement_line_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`StatementLineResponse`](#schema-statementlineresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/banking/imports/lines/{statement_line_id}/match` — Match a statement line to an existing journal line

_operationId:_ `match_ep_api_v1_banking_imports_lines__statement_line_id__match_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `statement_line_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`MatchRequest`](#schema-matchrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`StatementLineResponse`](#schema-statementlineresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/imports/lines/{statement_line_id}/suggestions` — Get match suggestions for a statement line

_operationId:_ `suggestions_ep_api_v1_banking_imports_lines__statement_line_id__suggestions_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `statement_line_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`JournalLineSuggestion`](#schema-journallinesuggestion)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/imports/{import_id}/lines` — List lines for an import

_operationId:_ `list_lines_api_v1_banking_imports__import_id__lines_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `import_id` | path | string(uuid) | ✓ |  |
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`StatementLineResponse`](#schema-statementlineresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/inter-account-transfers` — List inter-account transfers

_operationId:_ `list_iat_api_v1_banking_inter_account_transfers_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__inter_account_transfers__TransferResponse`](#schema-app__api__v1__endpoints__inter_account_transfers__transferresponse)[] | Successful Response |

### `POST /api/v1/banking/inter-account-transfers` — Create inter-account transfer

_operationId:_ `create_iat_api_v1_banking_inter_account_transfers_post`

**Request body**
- `application/json` → [`app__api__v1__endpoints__inter_account_transfers__TransferCreate`](#schema-app__api__v1__endpoints__inter_account_transfers__transfercreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`app__api__v1__endpoints__inter_account_transfers__TransferResponse`](#schema-app__api__v1__endpoints__inter_account_transfers__transferresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/inter-account-transfers/{transfer_id}` — Get inter-account transfer detail

_operationId:_ `get_iat_api_v1_banking_inter_account_transfers__transfer_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `transfer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__inter_account_transfers__TransferResponse`](#schema-app__api__v1__endpoints__inter_account_transfers__transferresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/banking/inter-account-transfers/{transfer_id}` — Edit inter-account transfer (refused if either leg is reconciled)

_operationId:_ `edit_iat_api_v1_banking_inter_account_transfers__transfer_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `transfer_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`TransferEdit`](#schema-transferedit)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__inter_account_transfers__TransferResponse`](#schema-app__api__v1__endpoints__inter_account_transfers__transferresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/banking/inter-account-transfers/{transfer_id}` — Delete inter-account transfer (refused if either leg is reconciled)

_operationId:_ `delete_iat_api_v1_banking_inter_account_transfers__transfer_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `transfer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/reconciliations` — List reconciliations (filtered by account/status)

_operationId:_ `list_reconciliations_api_v1_banking_reconciliations_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `account_id` | query | string(uuid) \| null |  |  |
| `recon_status` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/banking/reconciliations` — Start a reconciliation

_operationId:_ `create_reconciliation_api_v1_banking_reconciliations_post`

**Request body**
- `application/json` → [`ReconciliationCreateRequest`](#schema-reconciliationcreaterequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`ReconciliationDetailResponse`](#schema-reconciliationdetailresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/reconciliations/{reconciliation_id}` — Get reconciliation detail

_operationId:_ `get_reconciliation_api_v1_banking_reconciliations__reconciliation_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `reconciliation_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ReconciliationDetailResponse`](#schema-reconciliationdetailresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/banking/reconciliations/{reconciliation_id}/finalize` — Finalize a reconciliation (refuses if book != statement)

_operationId:_ `finalize_recon_api_v1_banking_reconciliations__reconciliation_id__finalize_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `reconciliation_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ReconciliationDetailResponse`](#schema-reconciliationdetailresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/banking/reconciliations/{reconciliation_id}/reopen` — Reopen a finalized reconciliation (admin)

_operationId:_ `reopen_recon_api_v1_banking_reconciliations__reconciliation_id__reopen_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `reconciliation_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ReconciliationDetailResponse`](#schema-reconciliationdetailresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/banking/reconciliations/{reconciliation_id}/toggle-line` — Include or exclude a journal line in the reconciliation

_operationId:_ `toggle_recon_line_api_v1_banking_reconciliations__reconciliation_id__toggle_line_patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `reconciliation_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ReconciliationLineToggle`](#schema-reconciliationlinetoggle)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ReconciliationDetailResponse`](#schema-reconciliationdetailresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/rules` — List statement-match rules

_operationId:_ `list_rules_api_v1_banking_rules_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RuleResponse`](#schema-ruleresponse)[] | Successful Response |

### `POST /api/v1/banking/rules` — Create a rule

_operationId:_ `create_rule_ep_api_v1_banking_rules_post`

**Request body**
- `application/json` → [`RuleCreate`](#schema-rulecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`RuleResponse`](#schema-ruleresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/banking/rules/from-line` — #316 P2: create a starter rule derived from a staged statement line

_operationId:_ `create_from_line_ep_api_v1_banking_rules_from_line_post`

**Request body**
- `application/json` → [`CreateFromLineBody`](#schema-createfromlinebody)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`RuleResponse`](#schema-ruleresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/banking/rules/imports/{import_id}/apply-rules` — Re-apply rules to an existing import's pending lines

_operationId:_ `apply_rules_ep_api_v1_banking_rules_imports__import_id__apply_rules_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `import_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/banking/rules/imports/{import_id}/preview` — #316 P2: dry-run preview of which rules would fire on each pending line

_operationId:_ `preview_rules_ep_api_v1_banking_rules_imports__import_id__preview_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `import_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/banking/rules/{rule_id}` — Update a rule

_operationId:_ `update_rule_ep_api_v1_banking_rules__rule_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `rule_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`RuleUpdate`](#schema-ruleupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RuleResponse`](#schema-ruleresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/banking/rules/{rule_id}` — Delete a rule

_operationId:_ `delete_rule_ep_api_v1_banking_rules__rule_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `rule_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: BatchOperations <a id="tag-batchoperations"></a>

### `GET /api/v1/batch/scopes` — List supported batch-op scopes and their soft-deactivate availability

_operationId:_ `list_scopes_api_v1_batch_scopes_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |

### `POST /api/v1/batch/sessions/{batch_id}/undo` — #327 P2: Undo a CSV import batch — hard-deletes the records it created

_operationId:_ `undo_batch_api_v1_batch_sessions__batch_id__undo_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `batch_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/batch/{scope}/activate` — Batch-reactivate master records

_operationId:_ `activate_ep_api_v1_batch__scope__activate_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |

**Request body**
- `application/json` → [`BatchRequest`](#schema-batchrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/batch/{scope}/deactivate` — Batch-deactivate master records (soft)

_operationId:_ `deactivate_ep_api_v1_batch__scope__deactivate_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |

**Request body**
- `application/json` → [`BatchRequest`](#schema-batchrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/batch/{scope}/delete` — Batch hard-delete (per-row error reporting on FK violations)

_operationId:_ `delete_ep_api_v1_batch__scope__delete_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |

**Request body**
- `application/json` → [`BatchRequest`](#schema-batchrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/batch/{scope}/import.csv` — #327 P2: Bulk-create master records from a CSV; returns batch_id for undo

_operationId:_ `import_csv_api_v1_batch__scope__import_csv_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |

**Request body**
- `multipart/form-data` → [`Body_import_csv_api_v1_batch__scope__import_csv_post`](#schema-body_import_csv_api_v1_batch__scope__import_csv_post)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: BillableExpenses <a id="tag-billableexpenses"></a>

### `GET /api/v1/billable-expenses` — List billable expenses

_operationId:_ `list_be_api_v1_billable_expenses_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `customer_id` | query | string(uuid) \| null |  |  |
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BillableExpenseResponse`](#schema-billableexpenseresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/billable-expenses` — Mark an expense as billable

_operationId:_ `create_be_api_v1_billable_expenses_post`

**Request body**
- `application/json` → [`BillableExpenseCreate`](#schema-billableexpensecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`BillableExpenseResponse`](#schema-billableexpenseresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/billable-expenses/{be_id}` — Update a pending billable expense

_operationId:_ `update_be_api_v1_billable_expenses__be_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `be_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`BillableExpenseUpdate`](#schema-billableexpenseupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BillableExpenseResponse`](#schema-billableexpenseresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/billable-expenses/{be_id}/add-to-invoice` — #263 P2: Append the rebillable amount as a pass-through line on an invoice

_operationId:_ `add_to_invoice_api_v1_billable_expenses__be_id__add_to_invoice_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `be_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`AddToInvoiceRequest`](#schema-addtoinvoicerequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BillableExpenseResponse`](#schema-billableexpenseresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/billable-expenses/{be_id}/void` — Void a pending billable expense

_operationId:_ `void_be_api_v1_billable_expenses__be_id__void_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `be_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BillableExpenseResponse`](#schema-billableexpenseresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Budgets <a id="tag-budgets"></a>

### `GET /api/v1/budgets` — List budgets

_operationId:_ `list_budgets_api_v1_budgets_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `year` | query | integer \| null |  |  |
| `account_id` | query | string(uuid) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BudgetResponse`](#schema-budgetresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/budgets/copy-year` — Copy all budgets from one year to another (idempotent — skips existing)

_operationId:_ `copy_year_api_v1_budgets_copy_year_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `from_year` | query | integer | ✓ |  |
| `to_year` | query | integer | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | object | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/budgets/upsert` — Upsert per (account, year, month)

_operationId:_ `upsert_budgets_api_v1_budgets_upsert_post`

**Request body**
- `application/json` → [`BudgetUpsertRequest`](#schema-budgetupsertrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BudgetResponse`](#schema-budgetresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/budgets/{budget_id}` — Delete a budget row

_operationId:_ `delete_budget_api_v1_budgets__budget_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `budget_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: COGS <a id="tag-cogs"></a>

### `GET /api/v1/cogs/fifo-flag` — #317: Get FIFO sales-COGS feature flag

_operationId:_ `get_fifo_flag_api_v1_cogs_fifo_flag_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`FifoFlagResponse`](#schema-fifoflagresponse) | Successful Response |

### `PUT /api/v1/cogs/fifo-flag` — #317: Set FIFO sales-COGS feature flag (admin only)

_operationId:_ `set_fifo_flag_api_v1_cogs_fifo_flag_put`

**Request body**
- `application/json` → [`FifoFlagUpdate`](#schema-fifoflagupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`FifoFlagResponse`](#schema-fifoflagresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/cogs/sales/{sale_id}/fifo-dry-run` — #317: Preview FIFO vs snapshot COGS for a sale (no mutation)

_operationId:_ `dry_run_api_v1_cogs_sales__sale_id__fifo_dry_run_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `sale_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`DryRunResponse`](#schema-dryrunresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Cameras <a id="tag-cameras"></a>

### `GET /api/v1/cameras` — List cameras

_operationId:_ `list_cameras_api_v1_cameras_get`

Returns paginated cameras with optional filtering.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  | Filter by active status |
| `assigned` | query | boolean \| null |  | Filter by printer assignment |
| `search` | query | string \| null |  | Search by name, slug, or stream name |
| `skip` | query | integer |  |  |
| `limit` | query | integer |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PaginatedCameras`](#schema-paginatedcameras) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/cameras` — Create a camera

_operationId:_ `create_camera_api_v1_cameras_post`

**Request body**
- `application/json` → [`CameraCreate`](#schema-cameracreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`CameraResponse`](#schema-cameraresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/cameras/test-snapshot` — Test camera snapshot by URL

_operationId:_ `test_camera_snapshot_api_v1_cameras_test_snapshot_post`

Proxies a snapshot from go2rtc using provided URL and stream name, for previewing before saving.

**Request body**
- `application/json` → object
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/cameras/{camera_id}` — Get camera by ID

_operationId:_ `get_camera_api_v1_cameras__camera_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `camera_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CameraResponse`](#schema-cameraresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/cameras/{camera_id}` — Update a camera

_operationId:_ `update_camera_api_v1_cameras__camera_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `camera_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`CameraUpdate`](#schema-cameraupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CameraResponse`](#schema-cameraresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/cameras/{camera_id}` — Deactivate a camera

_operationId:_ `delete_camera_api_v1_cameras__camera_id__delete`

Soft-deletes a camera by setting is_active=false and clearing printer assignment.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `camera_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/cameras/{camera_id}/assign` — Assign or unassign a camera to a printer

_operationId:_ `assign_camera_api_v1_cameras__camera_id__assign_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `camera_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → object
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CameraResponse`](#schema-cameraresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/cameras/{camera_id}/snapshot` — Get camera snapshot

_operationId:_ `get_camera_snapshot_api_v1_cameras__camera_id__snapshot_get`

Proxies a single MJPEG frame from go2rtc for health checking and CORS-free fallback.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `camera_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: CreditDebitNotes <a id="tag-creditdebitnotes"></a>

### `GET /api/v1/credit-notes` — List credit notes

_operationId:_ `list_cn_api_v1_credit_notes_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `customer_id` | query | string(uuid) \| null |  |  |
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/credit-notes` — Create a draft credit note

_operationId:_ `create_cn_api_v1_credit_notes_post`

**Request body**
- `application/json` → [`CreditNoteCreate`](#schema-creditnotecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/credit-notes/{note_id}` — Credit note detail

_operationId:_ `get_cn_api_v1_credit_notes__note_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `note_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/credit-notes/{note_id}/apply` — Apply credit note to an invoice

_operationId:_ `apply_cn_api_v1_credit_notes__note_id__apply_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `note_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ApplyRequest`](#schema-applyrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/credit-notes/{note_id}/issue` — Issue (post JE) a draft credit note

_operationId:_ `issue_cn_api_v1_credit_notes__note_id__issue_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `note_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/credit-notes/{note_id}/refund-in-cash` — #321 P2: Refund the unapplied portion of a credit note as cash

_operationId:_ `refund_in_cash_api_v1_credit_notes__note_id__refund_in_cash_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `note_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`RefundInCashRequest`](#schema-refundincashrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/credit-notes/{note_id}/void` — Void a credit note (reverses issue JE)

_operationId:_ `void_cn_api_v1_credit_notes__note_id__void_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `note_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/debit-notes` — List debit notes

_operationId:_ `list_dn_api_v1_debit_notes_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `vendor_id` | query | string(uuid) \| null |  |  |
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/debit-notes` — Create a draft debit note

_operationId:_ `create_dn_api_v1_debit_notes_post`

**Request body**
- `application/json` → [`DebitNoteCreate`](#schema-debitnotecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/debit-notes/{note_id}` — Debit note detail

_operationId:_ `get_dn_api_v1_debit_notes__note_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `note_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/debit-notes/{note_id}/apply` — Apply debit note to a bill

_operationId:_ `apply_dn_api_v1_debit_notes__note_id__apply_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `note_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ApplyRequest`](#schema-applyrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/debit-notes/{note_id}/issue` — Issue (post JE) a draft debit note

_operationId:_ `issue_dn_api_v1_debit_notes__note_id__issue_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `note_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/debit-notes/{note_id}/void` — Void a debit note (reverses issue JE)

_operationId:_ `void_dn_api_v1_debit_notes__note_id__void_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `note_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: CustomFields <a id="tag-customfields"></a>

### `POST /api/v1/custom-fields` — Create a custom field definition

_operationId:_ `create_def_api_v1_custom_fields_post`

**Request body**
- `application/json` → [`DefinitionCreate`](#schema-definitioncreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`DefinitionResponse`](#schema-definitionresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/custom-fields/values/{scope}/search` — #326 P2: Find record IDs whose custom-field {key} value matches

_operationId:_ `search_by_custom_field_api_v1_custom_fields_values__scope__search_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |
| `key` | query | string | ✓ |  |
| `value` | query | string | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/custom-fields/values/{scope}/{record_id}` — Read all custom-field values for a record

_operationId:_ `get_values_api_v1_custom_fields_values__scope___record_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |
| `record_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/custom-fields/values/{scope}/{record_id}` — Set custom-field values for a record

_operationId:_ `set_values_api_v1_custom_fields_values__scope___record_id__post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |
| `record_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ValueUpsert`](#schema-valueupsert)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/custom-fields/{def_id}` — Update a definition (cannot change field_type or scope)

_operationId:_ `update_def_api_v1_custom_fields__def_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `def_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`DefinitionUpdate`](#schema-definitionupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`DefinitionResponse`](#schema-definitionresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/custom-fields/{def_id}` — Soft-deactivate a definition (values preserved)

_operationId:_ `deactivate_def_api_v1_custom_fields__def_id__delete`

Phase 1 default: deactivate rather than hard-delete so existing
values aren't silently dropped. Use the dedicated hard-delete endpoint
when you really mean it.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `def_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/custom-fields/{def_id}/hard` — #326 P2: Hard-delete a definition (refuses if any values exist; pass ?force=true)

_operationId:_ `hard_delete_def_api_v1_custom_fields__def_id__hard_delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `def_id` | path | string(uuid) | ✓ |  |
| `force` | query | boolean |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/custom-fields/{scope}` — List custom field definitions for a scope

_operationId:_ `list_defs_ep_api_v1_custom_fields__scope__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |
| `include_inactive` | query | boolean |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`DefinitionResponse`](#schema-definitionresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Customers <a id="tag-customers"></a>

### `GET /api/v1/customers` — List customers

_operationId:_ `list_customers_api_v1_customers_get`

Returns customers with job counts. Supports search by name/email and pagination.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `search` | query | string \| null |  | Search by name or email |
| `skip` | query | integer |  | Number of records to skip |
| `limit` | query | integer |  | Max records to return |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CustomerResponse`](#schema-customerresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/customers` — Create a customer

_operationId:_ `create_customer_api_v1_customers_post`

Add a new customer record. Customers can be linked to jobs for tracking.

**Request body**
- `application/json` → [`CustomerCreate`](#schema-customercreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`CustomerResponse`](#schema-customerresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/customers/{customer_id}` — Get customer by ID

_operationId:_ `get_customer_api_v1_customers__customer_id__get`

Retrieve a single customer with their total job count.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `customer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CustomerResponse`](#schema-customerresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/customers/{customer_id}` — Update a customer

_operationId:_ `update_customer_api_v1_customers__customer_id__put`

Update one or more fields of a customer record.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `customer_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`CustomerUpdate`](#schema-customerupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CustomerResponse`](#schema-customerresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/customers/{customer_id}` — Delete a customer

_operationId:_ `delete_customer_api_v1_customers__customer_id__delete`

Permanently delete a customer record. Jobs linked to this customer will retain the customer_name field.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `customer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Dashboard <a id="tag-dashboard"></a>

### `GET /api/v1/dashboard/charts/materials` — Material usage breakdown

_operationId:_ `material_usage_chart_api_v1_dashboard_charts_materials_get`

Returns job counts per material for pie/bar charts. Supports date range filtering.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  | Start date (inclusive) |
| `date_to` | query | string(date) \| null |  | End date (inclusive) |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`MaterialUsageDataPoint`](#schema-materialusagedatapoint)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/dashboard/charts/profit-margins` — Profit margin by job

_operationId:_ `profit_margin_chart_api_v1_dashboard_charts_profit_margins_get`

Returns profit margin percentage per job for trend analysis. Supports date range filtering.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  | Start date (inclusive) |
| `date_to` | query | string(date) \| null |  | End date (inclusive) |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProfitMarginDataPoint`](#schema-profitmargindatapoint)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/dashboard/charts/revenue` — Revenue over time

_operationId:_ `revenue_chart_api_v1_dashboard_charts_revenue_get`

Returns daily revenue totals for charting. Supports date range filtering.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  | Start date (inclusive) |
| `date_to` | query | string(date) \| null |  | End date (inclusive) |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RevenueDataPoint`](#schema-revenuedatapoint)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/dashboard/finance-summary` — Finance dashboard summary

_operationId:_ `finance_summary_api_v1_dashboard_finance_summary_get`

Returns finance-focused dashboard widgets for cash, receivables, payables, inventory, tax, and payouts in transit.

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`FinanceDashboardSummary`](#schema-financedashboardsummary) | Successful Response |

### `GET /api/v1/dashboard/summary` — Dashboard summary metrics

_operationId:_ `get_summary_api_v1_dashboard_summary_get`

Returns aggregated business metrics: total jobs, pieces, revenue, costs, profit, average margin, and top material. Supports date range filtering.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  | Start date (inclusive) |
| `date_to` | query | string(date) \| null |  | End date (inclusive) |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`DashboardSummary`](#schema-dashboardsummary) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: DeliveryNotes <a id="tag-deliverynotes"></a>

### `GET /api/v1/delivery-notes` — List delivery notes

_operationId:_ `list_dn_api_v1_delivery_notes_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `invoice_id` | query | string(uuid) \| null |  |  |
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/delivery-notes` — Create a delivery note (draft)

_operationId:_ `create_dn_api_v1_delivery_notes_post`

**Request body**
- `application/json` → [`DNCreate`](#schema-dncreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/delivery-notes/{dn_id}` — Delivery note detail

_operationId:_ `get_dn_api_v1_delivery_notes__dn_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `dn_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/delivery-notes/{dn_id}` — Update delivery status / tracking / notes

_operationId:_ `update_dn_api_v1_delivery_notes__dn_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `dn_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`DNUpdate`](#schema-dnupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/delivery-notes/{dn_id}` — Delete a delivery note (only allowed in draft state)

_operationId:_ `delete_dn_api_v1_delivery_notes__dn_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `dn_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: DivisionsProjects <a id="tag-divisionsprojects"></a>

### `GET /api/v1/divisions` — List divisions

_operationId:_ `list_divisions_api_v1_divisions_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `include_inactive` | query | boolean |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`DivisionResponse`](#schema-divisionresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/divisions` — Create a division

_operationId:_ `create_division_api_v1_divisions_post`

**Request body**
- `application/json` → [`DivisionCreate`](#schema-divisioncreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`DivisionResponse`](#schema-divisionresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/divisions/{division_id}` — Update a division

_operationId:_ `update_division_api_v1_divisions__division_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `division_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`DivisionUpdate`](#schema-divisionupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`DivisionResponse`](#schema-divisionresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/divisions/{division_id}` — Delete a division

_operationId:_ `delete_division_api_v1_divisions__division_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `division_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/projects` — List projects

_operationId:_ `list_projects_api_v1_projects_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `include_archived` | query | boolean |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProjectResponse`](#schema-projectresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/projects` — Create a project

_operationId:_ `create_project_api_v1_projects_post`

**Request body**
- `application/json` → [`ProjectCreate`](#schema-projectcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`ProjectResponse`](#schema-projectresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/projects/{project_id}` — Update a project

_operationId:_ `update_project_api_v1_projects__project_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `project_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ProjectUpdate`](#schema-projectupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProjectResponse`](#schema-projectresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/projects/{project_id}` — Delete a project

_operationId:_ `delete_project_api_v1_projects__project_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `project_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Email <a id="tag-email"></a>

### `POST /api/v1/invoices/{invoice_id}/email` — Send an invoice via email

_operationId:_ `email_invoice_api_v1_invoices__invoice_id__email_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `invoice_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`EmailSendRequest`](#schema-emailsendrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`EmailDeliveryResponse`](#schema-emaildeliveryresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/invoices/{invoice_id}/email-deliveries` — List email send history for an invoice

_operationId:_ `list_invoice_deliveries_api_v1_invoices__invoice_id__email_deliveries_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `invoice_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`EmailDeliveryResponse`](#schema-emaildeliveryresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/quotes/{quote_id}/email` — Send a quote via email

_operationId:_ `email_quote_api_v1_quotes__quote_id__email_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `quote_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`EmailSendRequest`](#schema-emailsendrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`EmailDeliveryResponse`](#schema-emaildeliveryresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/quotes/{quote_id}/email-deliveries` — List email send history for a quote

_operationId:_ `list_quote_deliveries_api_v1_quotes__quote_id__email_deliveries_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `quote_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`EmailDeliveryResponse`](#schema-emaildeliveryresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: ExpenseClaims <a id="tag-expenseclaims"></a>

### `GET /api/v1/expense-claims` — List expense claims

_operationId:_ `list_claims_api_v1_expense_claims_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ClaimResponse`](#schema-claimresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/expense-claims` — Create an expense claim

_operationId:_ `create_api_v1_expense_claims_post`

**Request body**
- `application/json` → [`ClaimCreate`](#schema-claimcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`ClaimResponse`](#schema-claimresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/expense-claims/{claim_id}` — Get claim detail

_operationId:_ `get_one_api_v1_expense_claims__claim_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `claim_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ClaimResponse`](#schema-claimresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/expense-claims/{claim_id}/approve` — Approve a claim and post the JE

_operationId:_ `approve_ep_api_v1_expense_claims__claim_id__approve_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `claim_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ApproveRequest`](#schema-approverequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ClaimResponse`](#schema-claimresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/expense-claims/{claim_id}/cancel` — Cancel a claim

_operationId:_ `cancel_ep_api_v1_expense_claims__claim_id__cancel_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `claim_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ClaimResponse`](#schema-claimresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/expense-claims/{claim_id}/reimburse` — Reimburse an approved claim

_operationId:_ `reimburse_ep_api_v1_expense_claims__claim_id__reimburse_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `claim_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ReimburseRequest`](#schema-reimburserequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ClaimResponse`](#schema-claimresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/expense-claims/{claim_id}/reimburse-as-bill` — #324 P2: alternative reimbursement — convert owner liability to a vendor bill

_operationId:_ `reimburse_as_bill_ep_api_v1_expense_claims__claim_id__reimburse_as_bill_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `claim_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ReimburseAsBillRequest`](#schema-reimburseasbillrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ClaimResponse`](#schema-claimresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/expense-claims/{claim_id}/request-approval` — #324 P2: explicitly route a claim through the central approvals queue

_operationId:_ `request_approval_ep_api_v1_expense_claims__claim_id__request_approval_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `claim_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ClaimResponse`](#schema-claimresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/expense-claims/{claim_id}/submit` — Submit a draft claim (creates an ApprovalRequest when the approval-required setting is on)

_operationId:_ `submit_ep_api_v1_expense_claims__claim_id__submit_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `claim_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ClaimResponse`](#schema-claimresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: FixedAssets <a id="tag-fixedassets"></a>

### `GET /api/v1/fixed-assets` — List fixed assets

_operationId:_ `list_assets_api_v1_fixed_assets_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`FixedAssetResponse`](#schema-fixedassetresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/fixed-assets` — Register a new fixed asset

_operationId:_ `create_asset_api_v1_fixed_assets_post`

**Request body**
- `application/json` → [`FixedAssetCreate`](#schema-fixedassetcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`FixedAssetResponse`](#schema-fixedassetresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/fixed-assets/bulk-import.csv` — #325 P2: bulk-register fixed assets from a CSV upload

_operationId:_ `bulk_import_csv_api_v1_fixed_assets_bulk_import_csv_post`

CSV columns: name, acquired_on, acquisition_cost, useful_life_months
[, salvage_value, depreciation_method, declining_balance_rate,
   asset_tag, description, notes, asset_account_code,
   accumulated_depreciation_account_code, depreciation_expense_account_code]

Account codes resolve to IDs server-side. Defaults: 1700 / 1750 / 6700.
Returns one entry per row with `asset_id` or `error`.

**Request body**
- `multipart/form-data` → [`Body_bulk_import_csv_api_v1_fixed_assets_bulk_import_csv_post`](#schema-body_bulk_import_csv_api_v1_fixed_assets_bulk_import_csv_post)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/fixed-assets/post-depreciation` — Post depreciation through a period for selected (or all active) assets

_operationId:_ `post_dep_api_v1_fixed_assets_post_depreciation_post`

**Request body**
- `application/json` → [`DepreciationPostRequest`](#schema-depreciationpostrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/fixed-assets/post-monthly-due` — #325 P2: cron-friendly — post depreciation through the most recent completed month

_operationId:_ `post_monthly_due_api_v1_fixed_assets_post_monthly_due_post`

No-arg cron entry point. Posts depreciation through the last day of
the previous calendar month for every active asset that has any
catch-up entries due. Idempotent: re-running on the same day is a
no-op since `post_depreciation` skips already-posted periods.

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |

### `GET /api/v1/fixed-assets/{asset_id}` — Fixed asset detail with schedule

_operationId:_ `get_asset_api_v1_fixed_assets__asset_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `asset_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`FixedAssetDetail`](#schema-fixedassetdetail) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/fixed-assets/{asset_id}` — Update a fixed asset

_operationId:_ `update_asset_api_v1_fixed_assets__asset_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `asset_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`FixedAssetUpdate`](#schema-fixedassetupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`FixedAssetResponse`](#schema-fixedassetresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/fixed-assets/{asset_id}` — Delete a fixed asset (only if no entries and not disposed)

_operationId:_ `delete_asset_api_v1_fixed_assets__asset_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `asset_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/fixed-assets/{asset_id}/dispose` — Dispose a fixed asset (sale or write-off)

_operationId:_ `dispose_api_v1_fixed_assets__asset_id__dispose_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `asset_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`DisposeRequest`](#schema-disposerequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`FixedAssetResponse`](#schema-fixedassetresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: FormTemplates <a id="tag-formtemplates"></a>

### `POST /api/v1/form-templates` — Create a form template

_operationId:_ `create_template_api_v1_form_templates_post`

**Request body**
- `application/json` → [`TemplateCreate`](#schema-templatecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`TemplateResponse`](#schema-templateresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/form-templates/{scope}` — List form templates for a scope

_operationId:_ `list_templates_api_v1_form_templates__scope__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | string | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`TemplateResponse`](#schema-templateresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/form-templates/{template_id}` — Update a form template

_operationId:_ `update_template_api_v1_form_templates__template_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `template_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`TemplateUpdate`](#schema-templateupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`TemplateResponse`](#schema-templateresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/form-templates/{template_id}` — Delete a form template

_operationId:_ `delete_template_api_v1_form_templates__template_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `template_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Health <a id="tag-health"></a>

### `GET /health` — Health Check

_operationId:_ `health_check_health_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |

---

## Tag: Insights <a id="tag-insights"></a>

### `GET /api/v1/insights/status` — Get AI insights provider status

_operationId:_ `get_insights_status_api_v1_insights_status_get`

Returns the selected LLM provider, active model, and whether the provider is configured for read-only insights.

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InsightStatusResponse`](#schema-insightstatusresponse) | Successful Response |

### `POST /api/v1/insights/summary` — Generate AI business insights

_operationId:_ `create_insight_summary_api_v1_insights_summary_post`

Uses the configured LLM provider to generate a read-only operational summary grounded in app data.

**Request body**
- `application/json` → [`InsightRequest`](#schema-insightrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InsightSummaryResponse`](#schema-insightsummaryresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: IntangibleAssets <a id="tag-intangibleassets"></a>

### `GET /api/v1/intangible-assets` — List intangible assets

_operationId:_ `list_assets_api_v1_intangible_assets_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`IntangibleAssetResponse`](#schema-intangibleassetresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/intangible-assets` — Register a new intangible asset

_operationId:_ `create_asset_api_v1_intangible_assets_post`

**Request body**
- `application/json` → [`IntangibleAssetCreate`](#schema-intangibleassetcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`IntangibleAssetResponse`](#schema-intangibleassetresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/intangible-assets/post-amortization` — Post amortization through a period for selected (or all active) assets

_operationId:_ `post_amort_api_v1_intangible_assets_post_amortization_post`

**Request body**
- `application/json` → [`AmortizationPostRequest`](#schema-amortizationpostrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/intangible-assets/{asset_id}` — Intangible asset detail with schedule

_operationId:_ `get_asset_api_v1_intangible_assets__asset_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `asset_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`IntangibleAssetDetail`](#schema-intangibleassetdetail) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/intangible-assets/{asset_id}` — Update an intangible asset

_operationId:_ `update_asset_api_v1_intangible_assets__asset_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `asset_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`IntangibleAssetUpdate`](#schema-intangibleassetupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`IntangibleAssetResponse`](#schema-intangibleassetresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/intangible-assets/{asset_id}` — Delete an intangible asset (only if no entries and not disposed)

_operationId:_ `delete_asset_api_v1_intangible_assets__asset_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `asset_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/intangible-assets/{asset_id}/dispose` — Dispose an intangible asset

_operationId:_ `dispose_api_v1_intangible_assets__asset_id__dispose_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `asset_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`DisposeRequest`](#schema-disposerequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`IntangibleAssetResponse`](#schema-intangibleassetresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Inventory <a id="tag-inventory"></a>

### `GET /api/v1/inventory/alerts` — Get low-stock alerts

_operationId:_ `get_alerts_api_v1_inventory_alerts_get`

Returns products, materials, and supplies that are below their reorder points.

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InventoryAlert`](#schema-inventoryalert)[] | Successful Response |

### `GET /api/v1/inventory/default-fulfillment-location` — #318 P2: Get the default sale fulfillment location

_operationId:_ `get_default_fulfillment_location_api_v1_inventory_default_fulfillment_location_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`DefaultFulfillmentLocationResponse`](#schema-defaultfulfillmentlocationresponse) | Successful Response |

### `PUT /api/v1/inventory/default-fulfillment-location` — #318 P2: Set or clear the default sale fulfillment location

_operationId:_ `set_default_fulfillment_location_api_v1_inventory_default_fulfillment_location_put`

**Request body**
- `application/json` → [`DefaultFulfillmentLocationUpdate`](#schema-defaultfulfillmentlocationupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`DefaultFulfillmentLocationResponse`](#schema-defaultfulfillmentlocationresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/inventory/locations` — List inventory locations

_operationId:_ `list_locations_api_v1_inventory_locations_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `include_inactive` | query | boolean |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`LocationResponse`](#schema-locationresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/inventory/locations` — Create a location

_operationId:_ `create_location_api_v1_inventory_locations_post`

**Request body**
- `application/json` → [`LocationCreate`](#schema-locationcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`LocationResponse`](#schema-locationresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/inventory/locations/{location_id}` — Update a location

_operationId:_ `update_location_api_v1_inventory_locations__location_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `location_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`LocationUpdate`](#schema-locationupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`LocationResponse`](#schema-locationresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/inventory/locations/{location_id}` — Delete a location (only if no transfers reference it)

_operationId:_ `delete_location_api_v1_inventory_locations__location_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `location_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/inventory/locations/{location_id}/product-stock` — #318 P2: per-product on-hand at this location from the SoT

_operationId:_ `location_product_stock_api_v1_inventory_locations__location_id__product_stock_get`

Returns the per-(product, location) source-of-truth on-hand,
plus the in-transit qty arriving from `in_transit` transfers. The
snapshot endpoint above derives from completed transfers only and
is retained for back-compat; this endpoint is the authoritative
read.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `location_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`LocationStockRow`](#schema-locationstockrow)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/inventory/locations/{location_id}/stock-snapshot` — #318 P2: per-location product stock derived from completed transfers

_operationId:_ `location_stock_snapshot_api_v1_inventory_locations__location_id__stock_snapshot_get`

Returns net qty of each product currently sitting at this location,
computed from completed transfers (incoming - outgoing). Locations with
`kind=internal` typically also receive opening stock via the operator's
starting balance flow; the snapshot reflects only what's been moved.

For Phase 2-deeper, replace with a real per-location SoT.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `location_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/inventory/prevent-negative-stock` — #318 P2: read the prevent-negative-stock toggle

_operationId:_ `get_prevent_negative_stock_api_v1_inventory_prevent_negative_stock_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PreventNegativeStockResponse`](#schema-preventnegativestockresponse) | Successful Response |

### `PUT /api/v1/inventory/prevent-negative-stock` — #318 P2: set the prevent-negative-stock toggle (hard-block sales when on)

_operationId:_ `set_prevent_negative_stock_api_v1_inventory_prevent_negative_stock_put`

**Request body**
- `application/json` → [`PreventNegativeStockUpdate`](#schema-preventnegativestockupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PreventNegativeStockResponse`](#schema-preventnegativestockresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/inventory/reconcile` — Reconcile inventory from physical count

_operationId:_ `reconcile_inventory_api_v1_inventory_reconcile_post`

Compare counted stock to current stock and create the required variance adjustment through the existing audit/approval flow.

**Request body**
- `application/json` → [`InventoryReconcileRequest`](#schema-inventoryreconcilerequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InventoryReconcileResponse`](#schema-inventoryreconcileresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/inventory/starting-balances/inventory.csv` — #262 P2: Import inventory starting balances from CSV

_operationId:_ `import_inventory_starting_balances_api_v1_inventory_starting_balances_inventory_csv_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `as_of` | query | string(date) \| null |  | Posting date (defaults to today) |
| `force` | query | boolean |  | Override activity guard |

**Request body**
- `multipart/form-data` → [`Body_import_inventory_starting_balances_api_v1_inventory_starting_balances_inventory_csv_post`](#schema-body_import_inventory_starting_balances_api_v1_inventory_starting_balances_inventory_csv_post)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/inventory/transactions` — List inventory transactions

_operationId:_ `list_transactions_api_v1_inventory_transactions_get`

Returns paginated inventory transactions with filtering by product, type, and date range.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `product_id` | query | string(uuid) \| null |  | Filter by product ID |
| `type` | query | string \| null |  | Filter by transaction type |
| `date_from` | query | string(date) \| null |  | Start date (inclusive) |
| `date_to` | query | string(date) \| null |  | End date (inclusive) |
| `search` | query | string \| null |  | Search by product name or SKU |
| `sort_by` | query | string |  | Sort field (allowlisted) |
| `sort_dir` | query | string |  | Sort direction |
| `skip` | query | integer |  | Number of records to skip |
| `limit` | query | integer |  | Max records to return |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PaginatedTransactions`](#schema-paginatedtransactions) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/inventory/transactions` — Create stock adjustment

_operationId:_ `create_transaction_api_v1_inventory_transactions_post`

Manually adjust inventory stock. Use positive quantity to add, negative to remove.

**Request body**
- `application/json` → [`InventoryTransactionCreate`](#schema-inventorytransactioncreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`InventoryTransactionResponse`](#schema-inventorytransactionresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/inventory/transfers` — List transfers

_operationId:_ `list_transfers_api_v1_inventory_transfers_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__locations__TransferResponse`](#schema-app__api__v1__endpoints__locations__transferresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/inventory/transfers` — Create a transfer

_operationId:_ `create_transfer_ep_api_v1_inventory_transfers_post`

**Request body**
- `application/json` → [`app__api__v1__endpoints__locations__TransferCreate`](#schema-app__api__v1__endpoints__locations__transfercreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`app__api__v1__endpoints__locations__TransferResponse`](#schema-app__api__v1__endpoints__locations__transferresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/inventory/transfers/{transfer_id}` — Get transfer detail

_operationId:_ `get_transfer_api_v1_inventory_transfers__transfer_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `transfer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__locations__TransferResponse`](#schema-app__api__v1__endpoints__locations__transferresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/inventory/transfers/{transfer_id}/cancel` — Cancel a pending or in-transit transfer

_operationId:_ `cancel_ep_api_v1_inventory_transfers__transfer_id__cancel_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `transfer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__locations__TransferResponse`](#schema-app__api__v1__endpoints__locations__transferresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/inventory/transfers/{transfer_id}/receive` — Receive an in-transit transfer

_operationId:_ `receive_ep_api_v1_inventory_transfers__transfer_id__receive_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `transfer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__locations__TransferResponse`](#schema-app__api__v1__endpoints__locations__transferresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/inventory/transfers/{transfer_id}/ship` — Ship a pending transfer

_operationId:_ `ship_ep_api_v1_inventory_transfers__transfer_id__ship_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `transfer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__locations__TransferResponse`](#schema-app__api__v1__endpoints__locations__transferresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Invoices <a id="tag-invoices"></a>

### `GET /api/v1/invoices` — List invoices

_operationId:_ `list_invoices_api_v1_invoices_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status` | query | [`InvoiceStatus`](#schema-invoicestatus) \| null |  |  |
| `customer_id` | query | string(uuid) \| null |  |  |
| `skip` | query | integer |  |  |
| `limit` | query | integer |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PaginatedInvoices`](#schema-paginatedinvoices) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/invoices` — Create invoice

_operationId:_ `create_invoice_api_v1_invoices_post`

**Request body**
- `application/json` → [`InvoiceCreate`](#schema-invoicecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`InvoiceResponse`](#schema-invoiceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/invoices/credits` — Create customer credit

_operationId:_ `create_customer_credit_api_v1_invoices_credits_post`

**Request body**
- `application/json` → [`CustomerCreditCreate`](#schema-customercreditcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`CustomerCreditResponse`](#schema-customercreditresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/invoices/from-quote/{quote_id}` — Create invoice from accepted quote

_operationId:_ `create_invoice_from_quote_api_v1_invoices_from_quote__quote_id__post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `quote_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`InvoiceFromQuoteCreate`](#schema-invoicefromquotecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`InvoiceResponse`](#schema-invoiceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/invoices/late-fees/run-due` — #263 P2: Cron entry — generate late-fee invoices for overdue receivables

_operationId:_ `run_late_fees_due_ep_api_v1_invoices_late_fees_run_due_post`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |

### `POST /api/v1/invoices/payments` — Record payment

_operationId:_ `record_payment_api_v1_invoices_payments_post`

**Request body**
- `application/json` → [`PaymentCreate`](#schema-paymentcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`PaymentResponse`](#schema-paymentresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/invoices/reports/ar-aging` — A/R aging report

_operationId:_ `ar_aging_report_api_v1_invoices_reports_ar_aging_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `as_of_date` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ARAgingSummary`](#schema-aragingsummary) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/invoices/{invoice_id}` — Get invoice by ID

_operationId:_ `get_invoice_api_v1_invoices__invoice_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `invoice_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InvoiceResponse`](#schema-invoiceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/invoices/{invoice_id}` — Update invoice

_operationId:_ `update_invoice_api_v1_invoices__invoice_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `invoice_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`InvoiceUpdate`](#schema-invoiceupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InvoiceResponse`](#schema-invoiceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/invoices/{invoice_id}` — Delete invoice

_operationId:_ `delete_invoice_api_v1_invoices__invoice_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `invoice_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/invoices/{invoice_id}/apply-credit` — Apply credit to invoice

_operationId:_ `apply_invoice_credit_api_v1_invoices__invoice_id__apply_credit_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `invoice_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`CustomerCreditApply`](#schema-customercreditapply)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InvoiceResponse`](#schema-invoiceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/invoices/{invoice_id}/apply-payment` — Apply payment to invoice

_operationId:_ `apply_invoice_payment_api_v1_invoices__invoice_id__apply_payment_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `invoice_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`InvoicePaymentApply`](#schema-invoicepaymentapply)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InvoiceResponse`](#schema-invoiceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: JobDiscovery <a id="tag-jobdiscovery"></a>

### `GET /api/v1/job-discovery/candidates` — List discovered candidates

_operationId:_ `list_candidates_api_v1_job_discovery_candidates_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status_filter` | query | string \| null |  |  |
| `source_id` | query | string(uuid) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CandidateResponse`](#schema-candidateresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/job-discovery/candidates/{candidate_id}/promote` — Promote a candidate to a draft Job

_operationId:_ `promote_ep_api_v1_job_discovery_candidates__candidate_id__promote_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `candidate_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`PromoteRequest`](#schema-promoterequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CandidateResponse`](#schema-candidateresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/job-discovery/candidates/{candidate_id}/reject` — Reject a candidate without creating a job

_operationId:_ `reject_ep_api_v1_job_discovery_candidates__candidate_id__reject_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `candidate_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`RejectRequest`](#schema-rejectrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CandidateResponse`](#schema-candidateresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/job-discovery/sources` — List discovery sources

_operationId:_ `list_sources_api_v1_job_discovery_sources_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SourceResponse`](#schema-sourceresponse)[] | Successful Response |

### `POST /api/v1/job-discovery/sources` — Create discovery source

_operationId:_ `create_source_api_v1_job_discovery_sources_post`

**Request body**
- `application/json` → [`SourceCreate`](#schema-sourcecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`SourceResponse`](#schema-sourceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/job-discovery/sources/{source_id}` — Update discovery source

_operationId:_ `update_source_api_v1_job_discovery_sources__source_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `source_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`SourceUpdate`](#schema-sourceupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SourceResponse`](#schema-sourceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/job-discovery/sources/{source_id}` — Delete discovery source (cascades to candidates)

_operationId:_ `delete_source_api_v1_job_discovery_sources__source_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `source_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/job-discovery/sources/{source_id}/scan` — Manually trigger a discovery scan against a source

_operationId:_ `scan_source_ep_api_v1_job_discovery_sources__source_id__scan_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `source_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Jobs <a id="tag-jobs"></a>

### `GET /api/v1/jobs` — List jobs

_operationId:_ `list_jobs_api_v1_jobs_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status` | query | [`JobStatus`](#schema-jobstatus) \| null |  |  |
| `material_id` | query | string(uuid) \| null |  |  |
| `customer_id` | query | string(uuid) \| null |  |  |
| `printer_id` | query | string(uuid) \| null |  |  |
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |
| `search` | query | string \| null |  |  |
| `sort_by` | query | string |  |  |
| `sort_dir` | query | string |  |  |
| `skip` | query | integer |  |  |
| `limit` | query | integer |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PaginatedJobs`](#schema-paginatedjobs) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/jobs` — Create a job

_operationId:_ `create_job_api_v1_jobs_post`

**Request body**
- `application/json` → [`JobCreate`](#schema-jobcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`JobResponse`](#schema-jobresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/jobs/calculate` — Preview cost calculation

_operationId:_ `calculate_preview_api_v1_jobs_calculate_post`

**Request body**
- `application/json` → [`CalculateRequest`](#schema-calculaterequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CalculateResponse`](#schema-calculateresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/jobs/next-number` — Get next job number

_operationId:_ `get_next_job_number_api_v1_jobs_next_number_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date` | query | string(date) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/jobs/{job_id}` — Get job by ID

_operationId:_ `get_job_api_v1_jobs__job_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `job_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`JobResponse`](#schema-jobresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/jobs/{job_id}` — Update a job

_operationId:_ `update_job_api_v1_jobs__job_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `job_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`JobUpdate`](#schema-jobupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`JobResponse`](#schema-jobresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/jobs/{job_id}` — Delete a job

_operationId:_ `delete_job_api_v1_jobs__job_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `job_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/jobs/{job_id}/duplicate` — Duplicate a job

_operationId:_ `duplicate_job_api_v1_jobs__job_id__duplicate_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `job_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`JobResponse`](#schema-jobresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Kits <a id="tag-kits"></a>

### `GET /api/v1/kits` — List all kit products (products with at least one component)

_operationId:_ `list_kits_api_v1_kits_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |

### `GET /api/v1/kits/{kit_product_id}` — Get the kit definition for a product

_operationId:_ `get_kit_api_v1_kits__kit_product_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `kit_product_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`KitResponse`](#schema-kitresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/kits/{kit_product_id}` — Define or replace the kit's component list

_operationId:_ `upsert_kit_api_v1_kits__kit_product_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `kit_product_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`KitDefinitionRequest`](#schema-kitdefinitionrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`KitResponse`](#schema-kitresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/kits/{kit_product_id}` — Remove all components (the product stops being a kit)

_operationId:_ `clear_kit_api_v1_kits__kit_product_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `kit_product_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Materials <a id="tag-materials"></a>

### `GET /api/v1/materials` — List materials

_operationId:_ `list_materials_api_v1_materials_get`

Returns filament materials with optional filtering by active status and search by name/brand. Supports pagination.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `active` | query | boolean \| null |  | Filter by active status |
| `search` | query | string \| null |  | Search by name or brand |
| `skip` | query | integer |  | Number of records to skip |
| `limit` | query | integer |  | Max records to return |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`MaterialResponse`](#schema-materialresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/materials` — Create a material

_operationId:_ `create_material_api_v1_materials_post`

Add a new filament material. Cost per gram is automatically calculated from spool price and net usable grams.

**Request body**
- `application/json` → [`MaterialCreate`](#schema-materialcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`MaterialResponse`](#schema-materialresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/materials/resolve-from-print` — #230: Resolve loaded filament against catalog; create review-needed entry on miss

_operationId:_ `resolve_filament_api_v1_materials_resolve_from_print_post`

**Request body**
- `application/json` → [`FilamentResolveRequest`](#schema-filamentresolverequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/materials/{material_id}` — Get material by ID

_operationId:_ `get_material_api_v1_materials__material_id__get`

Retrieve a single filament material including its calculated cost per gram.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `material_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`MaterialResponse`](#schema-materialresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/materials/{material_id}` — Update a material

_operationId:_ `update_material_api_v1_materials__material_id__put`

Update one or more fields of a material. Cost per gram is recalculated if price or usable weight changes.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `material_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`MaterialUpdate`](#schema-materialupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`MaterialResponse`](#schema-materialresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/materials/{material_id}` — Deactivate a material

_operationId:_ `delete_material_api_v1_materials__material_id__delete`

Soft-deletes a material by setting active=false. Historical job data referencing this material is preserved.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `material_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/materials/{material_id}/receipts` — List material receipts/lots

_operationId:_ `list_material_receipts_api_v1_materials__material_id__receipts_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `material_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`MaterialReceiptResponse`](#schema-materialreceiptresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/materials/{material_id}/receipts` — Create material receipt/lot

_operationId:_ `create_receipt_api_v1_materials__material_id__receipts_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `material_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`MaterialReceiptCreate`](#schema-materialreceiptcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`MaterialReceiptResponse`](#schema-materialreceiptresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Merge <a id="tag-merge"></a>

### `POST /api/v1/merge/{scope}` — #262 P2: merge duplicate items into a survivor (scope: material|product)

_operationId:_ `merge_ep_api_v1_merge__scope__post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `scope` | path | enum("material", "product") | ✓ |  |

**Request body**
- `application/json` → [`MergeRequest`](#schema-mergerequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Orders <a id="tag-orders"></a>

### `GET /api/v1/purchase-orders` — List purchase orders

_operationId:_ `list_po_api_v1_purchase_orders_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `vendor_id` | query | string(uuid) \| null |  |  |
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/purchase-orders` — Create a purchase order

_operationId:_ `create_po_api_v1_purchase_orders_post`

**Request body**
- `application/json` → [`app__api__v1__endpoints__orders__POCreate`](#schema-app__api__v1__endpoints__orders__pocreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/purchase-orders/{order_id}` — Purchase order detail

_operationId:_ `get_po_api_v1_purchase_orders__order_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/purchase-orders/{order_id}/cancel` — Cancel a purchase order

_operationId:_ `cancel_po_api_v1_purchase_orders__order_id__cancel_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/purchase-orders/{order_id}/confirm` — Confirm a draft purchase order

_operationId:_ `confirm_po_api_v1_purchase_orders__order_id__confirm_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/purchase-orders/{order_id}/create-bill` — Create a bill from a confirmed purchase order (#261 Phase 2)

_operationId:_ `create_bill_from_po_api_v1_purchase_orders__order_id__create_bill_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |
| `expense_account_code` | query | string |  |  |
| `issue_date` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/sales-orders` — List sales orders

_operationId:_ `list_so_api_v1_sales_orders_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `customer_id` | query | string(uuid) \| null |  |  |
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/sales-orders` — Create a sales order

_operationId:_ `create_so_api_v1_sales_orders_post`

**Request body**
- `application/json` → [`SOCreate`](#schema-socreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/sales-orders/{order_id}` — Sales order detail

_operationId:_ `get_so_api_v1_sales_orders__order_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/sales-orders/{order_id}/cancel` — Cancel a sales order

_operationId:_ `cancel_so_api_v1_sales_orders__order_id__cancel_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/sales-orders/{order_id}/confirm` — Confirm a draft sales order

_operationId:_ `confirm_so_api_v1_sales_orders__order_id__confirm_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/sales-orders/{order_id}/create-invoice` — Create an invoice from a confirmed sales order (#261 Phase 2)

_operationId:_ `create_invoice_from_so_api_v1_sales_orders__order_id__create_invoice_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |
| `issue_date` | query | string(date) \| null |  |  |
| `due_date` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Printers <a id="tag-printers"></a>

### `GET /api/v1/printers` — List printers

_operationId:_ `list_printers_api_v1_printers_get`

Returns paginated printers with optional filtering by active status, printer status, and search.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  | Filter by active status |
| `status` | query | string \| null |  | Filter by printer status |
| `search` | query | string \| null |  | Search by printer name, slug, model, or location |
| `skip` | query | integer |  | Number of records to skip |
| `limit` | query | integer |  | Max records to return |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PaginatedPrinters`](#schema-paginatedprinters) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/printers` — Create a printer

_operationId:_ `create_printer_api_v1_printers_post`

Create a new tracked printer resource.

**Request body**
- `application/json` → [`PrinterCreate`](#schema-printercreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`PrinterResponse`](#schema-printerresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/printers/{printer_id}` — Get printer by ID

_operationId:_ `get_printer_api_v1_printers__printer_id__get`

Retrieve a single printer record.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `printer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PrinterResponse`](#schema-printerresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/printers/{printer_id}` — Update a printer

_operationId:_ `update_printer_api_v1_printers__printer_id__put`

Update one or more fields of a printer.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `printer_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`PrinterUpdate`](#schema-printerupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PrinterResponse`](#schema-printerresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/printers/{printer_id}` — Deactivate a printer

_operationId:_ `delete_printer_api_v1_printers__printer_id__delete`

Soft-deletes a printer by setting is_active=false.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `printer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/printers/{printer_id}/refresh` — Refresh live printer status

_operationId:_ `refresh_printer_api_v1_printers__printer_id__refresh_post`

Force a live provider refresh for a configured printer.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `printer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PrinterResponse`](#schema-printerresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/printers/{printer_id}/test-connection` — Test printer monitoring connection

_operationId:_ `test_connection_api_v1_printers__printer_id__test_connection_post`

Tests connectivity to the configured monitoring provider without changing saved live state.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `printer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PrinterConnectionTestResponse`](#schema-printerconnectiontestresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/printers/{printer_id}/thumbnail` — Get current print thumbnail

_operationId:_ `get_printer_thumbnail_api_v1_printers__printer_id__thumbnail_get`

Fetches the active Moonraker print thumbnail through the backend to avoid frontend CORS and path encoding issues.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `printer_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: ProductionOrders <a id="tag-productionorders"></a>

### `GET /api/v1/production-orders` — List production orders

_operationId:_ `list_orders_api_v1_production_orders_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status_filter` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`POResponse`](#schema-poresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/production-orders` — Create a planned production order with BOM snapshot

_operationId:_ `create_api_v1_production_orders_post`

**Request body**
- `application/json` → [`app__api__v1__endpoints__production_orders__POCreate`](#schema-app__api__v1__endpoints__production_orders__pocreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`POResponse`](#schema-poresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/production-orders/finished-goods/{product_id}` — List finished-goods layers for a product (Phase 2 will use these for COGS)

_operationId:_ `list_layers_api_v1_production_orders_finished_goods__product_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `product_id` | path | string(uuid) | ✓ |  |
| `only_remaining` | query | boolean |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/production-orders/{order_id}` — Production order detail with consumption snapshot

_operationId:_ `get_order_api_v1_production_orders__order_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PODetail`](#schema-podetail) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/production-orders/{order_id}/cancel` — Cancel a planned order (no GL impact)

_operationId:_ `cancel_ep_api_v1_production_orders__order_id__cancel_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`POResponse`](#schema-poresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/production-orders/{order_id}/close` — Close a planned production order — FIFO-consume materials, post JE, create finished-goods layer

_operationId:_ `close_ep_api_v1_production_orders__order_id__close_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `order_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`POResponse`](#schema-poresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Products <a id="tag-products"></a>

### `GET /api/v1/products` — List products

_operationId:_ `list_products_api_v1_products_get`

Returns paginated product catalog with filtering by active status, material, stock level, and search.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  | Filter by active status |
| `material_id` | query | string(uuid) \| null |  | Filter by material ID |
| `low_stock` | query | boolean \| null |  | Filter products below reorder point |
| `search` | query | string \| null |  | Search by name, SKU, or UPC |
| `sort_by` | query | string |  | Sort field (allowlisted) |
| `sort_dir` | query | string |  | Sort direction |
| `skip` | query | integer |  | Number of records to skip |
| `limit` | query | integer |  | Max records to return |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PaginatedProducts`](#schema-paginatedproducts) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/products` — Create a product

_operationId:_ `create_product_api_v1_products_post`

Create a new product in the catalog. SKU is auto-generated in format PRD-{MATERIAL}-{NNNN}.

**Request body**
- `application/json` → [`ProductCreate`](#schema-productcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`ProductResponse`](#schema-productresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/products/barcode/generate` — Generate a unique internal UPC-A barcode

_operationId:_ `generate_product_barcode_api_v1_products_barcode_generate_post`

Returns a unique 12-digit UPC-A value from the app's internal-use `04` namespace. The value includes a valid UPC-A check digit and is intended for in-store/product-studio barcode workflows, not manufacturer-issued GS1 retail UPC assignment.

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProductBarcodeGenerateResponse`](#schema-productbarcodegenerateresponse) | Successful Response |

### `GET /api/v1/products/{product_id}` — Get product by ID

_operationId:_ `get_product_api_v1_products__product_id__get`

Retrieve a single product with its inventory details.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `product_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProductResponse`](#schema-productresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/products/{product_id}` — Update a product

_operationId:_ `update_product_api_v1_products__product_id__put`

Update one or more fields of a product.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `product_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ProductUpdate`](#schema-productupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProductResponse`](#schema-productresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/products/{product_id}` — Deactivate a product

_operationId:_ `delete_product_api_v1_products__product_id__delete`

Soft-deletes a product by setting is_active=false.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `product_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/products/{product_id}/barcode` — Generate a printable barcode for a product

_operationId:_ `get_product_barcode_api_v1_products__product_id__barcode_get`

Returns a PNG-encoded barcode or QR code for the given product. `format=code128` (default) encodes the product SKU; `format=upc` encodes the UPC-A value and requires the product to have a 12-digit UPC; `format=qr` encodes either the UPC/SKU or the product URL when `url=1` is set.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `product_id` | path | string(uuid) | ✓ |  |
| `format` | query | enum("code128", "upc", "qr") |  | Barcode format |
| `size` | query | integer |  | Visual size hint (1-20) |
| `url` | query | boolean |  | When format=qr, encode the public product URL instead of UPC/SKU. |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/products/{product_id}/bom` — Get a product bill of materials

_operationId:_ `get_product_bom_api_v1_products__product_id__bom_get`

Returns BOM component rows with estimated cost, stock readiness, and buildable quantity.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `product_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProductBOMSummary`](#schema-productbomsummary) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/products/{product_id}/bom` — Replace a product bill of materials

_operationId:_ `put_product_bom_api_v1_products__product_id__bom_put`

Replaces all BOM rows for a product. Editing the BOM does not consume inventory or change product unit cost.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `product_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ProductBOMReplace`](#schema-productbomreplace)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProductBOMSummary`](#schema-productbomsummary) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/products/{product_id}/bom/availability` — Get product BOM availability

_operationId:_ `get_product_bom_availability_api_v1_products__product_id__bom_availability_get`

Returns current stock blockers and buildable quantity for a product BOM.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `product_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProductBOMAvailability`](#schema-productbomavailability) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Quotes <a id="tag-quotes"></a>

### `GET /api/v1/quotes` — List quotes

_operationId:_ `list_quotes_api_v1_quotes_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status` | query | [`QuoteStatus`](#schema-quotestatus) \| null |  |  |
| `customer_id` | query | string(uuid) \| null |  |  |
| `search` | query | string \| null |  |  |
| `skip` | query | integer |  |  |
| `limit` | query | integer |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PaginatedQuotes`](#schema-paginatedquotes) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/quotes` — Create quote

_operationId:_ `create_quote_api_v1_quotes_post`

**Request body**
- `application/json` → [`QuoteCreate`](#schema-quotecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`QuoteResponse`](#schema-quoteresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/quotes/{quote_id}` — Get quote by ID

_operationId:_ `get_quote_api_v1_quotes__quote_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `quote_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`QuoteResponse`](#schema-quoteresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/quotes/{quote_id}` — Update quote

_operationId:_ `update_quote_api_v1_quotes__quote_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `quote_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`QuoteUpdate`](#schema-quoteupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`QuoteResponse`](#schema-quoteresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/quotes/{quote_id}` — Delete quote

_operationId:_ `delete_quote_api_v1_quotes__quote_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `quote_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/quotes/{quote_id}/convert-to-job` — Convert accepted quote to job

_operationId:_ `convert_quote_to_job_api_v1_quotes__quote_id__convert_to_job_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `quote_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`QuoteConvertToJob`](#schema-quoteconverttojob)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | object | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Rates <a id="tag-rates"></a>

### `GET /api/v1/rates` — List rates

_operationId:_ `list_rates_api_v1_rates_get`

Returns business rates (labor, machine, overhead) with optional filtering by active status. Supports pagination.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `active` | query | boolean \| null |  | Filter by active status |
| `skip` | query | integer |  | Number of records to skip |
| `limit` | query | integer |  | Max records to return |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RateResponse`](#schema-rateresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/rates` — Create a rate

_operationId:_ `create_rate_api_v1_rates_post`

Add a new business rate (e.g. labor rate, machine rate, overhead percentage).

**Request body**
- `application/json` → [`RateCreate`](#schema-ratecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`RateResponse`](#schema-rateresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/rates/{rate_id}` — Get rate by ID

_operationId:_ `get_rate_api_v1_rates__rate_id__get`

Retrieve a single business rate.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `rate_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RateResponse`](#schema-rateresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/rates/{rate_id}` — Update a rate

_operationId:_ `update_rate_api_v1_rates__rate_id__put`

Update one or more fields of a business rate.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `rate_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`RateUpdate`](#schema-rateupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RateResponse`](#schema-rateresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/rates/{rate_id}` — Deactivate a rate

_operationId:_ `delete_rate_api_v1_rates__rate_id__delete`

Soft-deletes a rate by setting active=false.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `rate_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: RecurringInvoices <a id="tag-recurringinvoices"></a>

### `GET /api/v1/recurring-invoices` — List recurring invoices

_operationId:_ `list_recurring_api_v1_recurring_invoices_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `active_only` | query | boolean |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RecurringInvoiceResponse`](#schema-recurringinvoiceresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/recurring-invoices` — Create a recurring invoice rule

_operationId:_ `create_recurring_api_v1_recurring_invoices_post`

**Request body**
- `application/json` → [`RecurringInvoiceCreate`](#schema-recurringinvoicecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`RecurringInvoiceResponse`](#schema-recurringinvoiceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/recurring-invoices/run-due` — Cron entry point — generate due invoices and advance schedules

_operationId:_ `run_due_ep_api_v1_recurring_invoices_run_due_post`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |

### `GET /api/v1/recurring-invoices/{recurring_id}` — Get recurring invoice

_operationId:_ `get_recurring_api_v1_recurring_invoices__recurring_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `recurring_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RecurringInvoiceResponse`](#schema-recurringinvoiceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/recurring-invoices/{recurring_id}` — Update a recurring invoice

_operationId:_ `update_recurring_api_v1_recurring_invoices__recurring_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `recurring_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`RecurringInvoiceUpdate`](#schema-recurringinvoiceupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`RecurringInvoiceResponse`](#schema-recurringinvoiceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/recurring-invoices/{recurring_id}` — Delete a recurring invoice

_operationId:_ `delete_recurring_api_v1_recurring_invoices__recurring_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `recurring_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/recurring-invoices/{recurring_id}/run-now` — Generate one invoice immediately and advance the schedule

_operationId:_ `run_now_ep_api_v1_recurring_invoices__recurring_id__run_now_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `recurring_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__recurring_invoices__RunResponse`](#schema-app__api__v1__endpoints__recurring_invoices__runresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/recurring-invoices/{recurring_id}/runs` — Run history for a recurring invoice

_operationId:_ `list_runs_api_v1_recurring_invoices__recurring_id__runs_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `recurring_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__recurring_invoices__RunResponse`](#schema-app__api__v1__endpoints__recurring_invoices__runresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/recurring-invoices/{recurring_id}/skip-next` — Advance the schedule without generating an invoice

_operationId:_ `skip_ep_api_v1_recurring_invoices__recurring_id__skip_next_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `recurring_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`app__api__v1__endpoints__recurring_invoices__RunResponse`](#schema-app__api__v1__endpoints__recurring_invoices__runresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Reports <a id="tag-reports"></a>

### `GET /api/v1/reports/account-drill-down` — List source journal lines behind a report cell (#322 P2)

_operationId:_ `account_drill_down_api_v1_reports_account_drill_down_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `account_id` | query | string(uuid) | ✓ |  |
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`AccountDrillDownResponse`](#schema-accountdrilldownresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/ap-aging` — A/P aging report

_operationId:_ `ap_aging_report_api_v1_reports_ap_aging_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `as_of_date` | query | string(date) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`APAgingSummary`](#schema-apagingsummary) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/ar-aging` — A/R aging report

_operationId:_ `ar_aging_report_api_v1_reports_ar_aging_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `as_of_date` | query | string(date) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ARAgingReportResponse`](#schema-aragingreportresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/balance-sheet` — Balance sheet

_operationId:_ `balance_sheet_report_api_v1_reports_balance_sheet_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `as_of_date` | query | string(date) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`BalanceSheetResponse`](#schema-balancesheetresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/cash-flow` — Cash flow summary

_operationId:_ `cash_flow_report_api_v1_reports_cash_flow_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`CashFlowSummaryResponse`](#schema-cashflowsummaryresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/cogs-breakdown` — COGS breakdown report

_operationId:_ `cogs_breakdown_report_api_v1_reports_cogs_breakdown_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |
| `period` | query | enum("daily", "weekly", "monthly", "yearly") |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`COGSBreakdownSummary`](#schema-cogsbreakdownsummary) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/inventory` — Inventory report

_operationId:_ `inventory_report_api_v1_reports_inventory_get`

Stock levels with valuation, material usage, and turnover rates.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InventoryReportResponse`](#schema-inventoryreportresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/inventory-valuation` — Inventory valuation report

_operationId:_ `inventory_valuation_report_api_v1_reports_inventory_valuation_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`InventoryValuationSummary`](#schema-inventoryvaluationsummary) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/inventory/csv` — Export inventory report as CSV

_operationId:_ `inventory_csv_api_v1_reports_inventory_csv_get`

Download stock levels as a CSV file.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/pl` — Profit & Loss report

_operationId:_ `pl_report_api_v1_reports_pl_get`

Combined P&L from production jobs and sales.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |
| `period` | query | enum("daily", "weekly", "monthly", "yearly") |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PLReportResponse`](#schema-plreportresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/pl-accrual` — Accrual-basis P&L

_operationId:_ `pl_accrual_report_api_v1_reports_pl_accrual_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |
| `division_id` | query | string(uuid) \| null |  | #328 P2: filter to one division |
| `project_id` | query | string(uuid) \| null |  | #328 P2: filter to one project |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProfitAndLossResponse`](#schema-profitandlossresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/pl-cash` — Cash-basis P&L

_operationId:_ `pl_cash_report_api_v1_reports_pl_cash_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProfitAndLossResponse`](#schema-profitandlossresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/pl-comparison` — P&L for current period side-by-side with a prior period (#322 P2)

_operationId:_ `pl_comparison_report_api_v1_reports_pl_comparison_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) | ✓ |  |
| `date_to` | query | string(date) | ✓ |  |
| `compare_to_start` | query | string(date) | ✓ |  |
| `compare_to_end` | query | string(date) | ✓ |  |
| `basis` | query | string |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProfitAndLossComparisonResponse`](#schema-profitandlosscomparisonresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/pl/csv` — Export P&L report as CSV

_operationId:_ `pl_csv_api_v1_reports_pl_csv_get`

Download P&L period data as a CSV file.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |
| `period` | query | enum("daily", "weekly", "monthly", "yearly") |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/receipts-payments-summary` — Receipts & Payments Summary — categorized cash movements grouped by GL account

_operationId:_ `receipts_payments_summary_report_api_v1_reports_receipts_payments_summary_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/receipts-payments-summary.csv` — Receipts & Payments Summary as CSV

_operationId:_ `receipts_payments_csv_api_v1_reports_receipts_payments_summary_csv_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/sales` — Sales report

_operationId:_ `sales_report_api_v1_reports_sales_get`

Sales over time, top products, and channel breakdown.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |
| `channel_id` | query | string(uuid) \| null |  |  |
| `payment_method` | query | string \| null |  |  |
| `period` | query | enum("daily", "weekly", "monthly", "yearly") |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SalesReportResponse`](#schema-salesreportresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/sales/csv` — Export sales report as CSV

_operationId:_ `sales_csv_api_v1_reports_sales_csv_get`

Download sales period data as a CSV file.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |
| `channel_id` | query | string(uuid) \| null |  |  |
| `payment_method` | query | string \| null |  |  |
| `period` | query | enum("daily", "weekly", "monthly", "yearly") |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/tax-liability` — Tax liability summary

_operationId:_ `tax_liability_report_api_v1_reports_tax_liability_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`TaxLiabilityReportResponse`](#schema-taxliabilityreportresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/trial-balance` — Trial balance — debit + credit columns at a point in time

_operationId:_ `trial_balance_report_api_v1_reports_trial_balance_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `as_of_date` | query | string(date) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/reports/trial-balance.csv` — Trial balance as CSV

_operationId:_ `trial_balance_csv_api_v1_reports_trial_balance_csv_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `as_of_date` | query | string(date) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Sales <a id="tag-sales"></a>

### `POST /api/v1/pos/checkout` — Create a POS checkout sale

_operationId:_ `pos_checkout_api_v1_pos_checkout_post`

Creates a point-of-sale checkout using the standard sales tables and inventory path. POS sales are identified by the dedicated POS sales channel and stored as normal sales.

**Request body**
- `application/json` → [`POSCheckoutCreate`](#schema-poscheckoutcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`SaleResponse`](#schema-saleresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/pos/scan/resolve` — Resolve a barcode scan for POS

_operationId:_ `resolve_scan_api_v1_pos_scan_resolve_post`

Resolves an exact UPC/barcode match into a sellable active product for keyboard-wedge POS scanners. Returns a conflict for duplicates, inactive products, or out-of-stock products.

**Request body**
- `application/json` → [`POSProductScanRequest`](#schema-posproductscanrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProductResponse`](#schema-productresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/sales` — List sales

_operationId:_ `list_sales_api_v1_sales_get`

Returns paginated sales with filtering by status, channel, customer, and date range.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `status` | query | [`SaleStatus`](#schema-salestatus) \| null |  | Filter by status |
| `channel_id` | query | string(uuid) \| null |  | Filter by channel |
| `payment_method` | query | string \| null |  | Filter by payment method |
| `customer_id` | query | string(uuid) \| null |  | Filter by customer |
| `date_from` | query | string(date) \| null |  | Start date |
| `date_to` | query | string(date) \| null |  | End date |
| `search` | query | string \| null |  | Search by sale number or customer name |
| `sort_by` | query | string |  | Sort field (allowlisted) |
| `sort_dir` | query | string |  | Sort direction |
| `skip` | query | integer |  |  |
| `limit` | query | integer |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`PaginatedSales`](#schema-paginatedsales) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/sales` — Create a sale

_operationId:_ `create_sale_api_v1_sales_post`

Create a sale with line items. Platform fees are auto-computed from channel. Inventory is deducted for product items.

**Request body**
- `application/json` → [`SaleCreate`](#schema-salecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`SaleResponse`](#schema-saleresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/sales/channels` — List sales channels

_operationId:_ `list_channels_api_v1_sales_channels_get`

Returns all sales channels with optional active filter.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  | Filter by active status |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SalesChannelResponse`](#schema-saleschannelresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/sales/channels` — Create sales channel

_operationId:_ `create_channel_api_v1_sales_channels_post`

**Request body**
- `application/json` → [`SalesChannelCreate`](#schema-saleschannelcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`SalesChannelResponse`](#schema-saleschannelresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/sales/channels/{channel_id}` — Get sales channel

_operationId:_ `get_channel_api_v1_sales_channels__channel_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `channel_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SalesChannelResponse`](#schema-saleschannelresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/sales/channels/{channel_id}` — Update sales channel

_operationId:_ `update_channel_api_v1_sales_channels__channel_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `channel_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`SalesChannelUpdate`](#schema-saleschannelupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SalesChannelResponse`](#schema-saleschannelresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/sales/channels/{channel_id}` — Deactivate sales channel

_operationId:_ `delete_channel_api_v1_sales_channels__channel_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `channel_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/sales/metrics` — Sales metrics

_operationId:_ `get_metrics_api_v1_sales_metrics_get`

Aggregated sales metrics: revenue, units, AOV, refund rate, by-channel breakdown.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |
| `channel_id` | query | string(uuid) \| null |  |  |
| `payment_method` | query | string \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SalesMetrics`](#schema-salesmetrics) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/sales/{sale_id}` — Get sale by ID

_operationId:_ `get_sale_api_v1_sales__sale_id__get`

Retrieve a sale with its line items.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `sale_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SaleResponse`](#schema-saleresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/sales/{sale_id}` — Update a sale

_operationId:_ `update_sale_api_v1_sales__sale_id__put`

Update sale details (not line items). Status changes to 'refunded' restore inventory.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `sale_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`SaleUpdate`](#schema-saleupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SaleResponse`](#schema-saleresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/sales/{sale_id}` — Delete a sale

_operationId:_ `delete_sale_api_v1_sales__sale_id__delete`

Soft-deletes a sale.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `sale_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/sales/{sale_id}/refund` — Refund a sale

_operationId:_ `refund_sale_api_v1_sales__sale_id__refund_post`

Mark a sale as refunded and restore inventory.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `sale_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`RefundRequestBody`](#schema-refundrequestbody)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SaleResponse`](#schema-saleresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/sales/{sale_id}/shipping-label` — Get browser-printable shipping label

_operationId:_ `get_shipping_label_api_v1_sales__sale_id__shipping_label_get`

Returns a 4x6 browser-printable HTML shipping label for workstation-local printing.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `sale_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | string | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/sales/{sale_id}/shipping-label/mark-printed` — Mark shipping label as printed

_operationId:_ `mark_sale_shipping_label_printed_api_v1_sales__sale_id__shipping_label_mark_printed_post`

Records operator-confirmed shipping label printing after the workstation successfully prints the label.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `sale_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SaleResponse`](#schema-saleresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Settings <a id="tag-settings"></a>

### `GET /api/v1/settings` — List all settings

_operationId:_ `list_settings_api_v1_settings_get`

Admin-only. Returns every business and AI configuration setting, including provider configuration records.

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SettingResponse`](#schema-settingresponse)[] | Successful Response |

### `PUT /api/v1/settings/bulk` — Bulk update settings

_operationId:_ `bulk_update_settings_api_v1_settings_bulk_put`

Admin-only. Update multiple settings in a single request. Keys that don't exist are silently skipped.

**Request body**
- `application/json` → [`BulkSettingUpdate`](#schema-bulksettingupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SettingResponse`](#schema-settingresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/settings/{key}` — Get a setting by key

_operationId:_ `get_setting_api_v1_settings__key__get`

Admin-only. Retrieve a single configuration setting by its unique key.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `key` | path | string | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SettingResponse`](#schema-settingresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/settings/{key}` — Update a setting

_operationId:_ `update_setting_api_v1_settings__key__put`

Admin-only. Update the value of an existing configuration setting.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `key` | path | string | ✓ |  |

**Request body**
- `application/json` → [`SettingUpdate`](#schema-settingupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SettingResponse`](#schema-settingresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Settlements <a id="tag-settlements"></a>

### `GET /api/v1/settlements` — List marketplace settlements

_operationId:_ `list_settlements_api_v1_settlements_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `channel_id` | query | string(uuid) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`MarketplaceSettlementResponse`](#schema-marketplacesettlementresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/settlements` — Create marketplace settlement (admin only)

_operationId:_ `create_settlement_api_v1_settlements_post`

**Request body**
- `application/json` → [`MarketplaceSettlementCreate`](#schema-marketplacesettlementcreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`MarketplaceSettlementResponse`](#schema-marketplacesettlementresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/settlements/reports/reconciliation` — Settlement reconciliation report (admin only)

_operationId:_ `settlement_reconciliation_report_api_v1_settlements_reports_reconciliation_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `channel_id` | query | string(uuid) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SettlementReconciliationSummary`](#schema-settlementreconciliationsummary) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Supplies <a id="tag-supplies"></a>

### `GET /api/v1/supplies` — List supplies

_operationId:_ `list_supplies_api_v1_supplies_get`

Returns purchased/shop supplies with optional active, category, and text filtering.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `active` | query | boolean \| null |  | Filter by active status |
| `category` | query | string \| null |  | Filter by category |
| `search` | query | string \| null |  | Search by name, SKU, category, or supplier |
| `skip` | query | integer |  |  |
| `limit` | query | integer |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SupplyResponse`](#schema-supplyresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/supplies` — Create a supply

_operationId:_ `create_supply_api_v1_supplies_post`

**Request body**
- `application/json` → [`SupplyCreate`](#schema-supplycreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`SupplyResponse`](#schema-supplyresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/supplies/{supply_id}` — Get supply by ID

_operationId:_ `get_supply_api_v1_supplies__supply_id__get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `supply_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SupplyResponse`](#schema-supplyresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/supplies/{supply_id}` — Update a supply

_operationId:_ `update_supply_api_v1_supplies__supply_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `supply_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`SupplyUpdate`](#schema-supplyupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SupplyResponse`](#schema-supplyresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /api/v1/supplies/{supply_id}` — Archive a supply

_operationId:_ `delete_supply_api_v1_supplies__supply_id__delete`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `supply_id` | path | string(uuid) | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `204` |  | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/supplies/{supply_id}/adjust` — Adjust supply quantity

_operationId:_ `adjust_supply_api_v1_supplies__supply_id__adjust_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `supply_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`SupplyAdjust`](#schema-supplyadjust)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`SupplyResponse`](#schema-supplyresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Tax <a id="tag-tax"></a>

### `POST /api/v1/tax/compute` — Compute tax breakdown for a subtotal against a profile (#258 Phase 2)

_operationId:_ `compute_tax_api_v1_tax_compute_post`

Returns one row per layer for compound profiles, one for single-rate.
Each row carries `component_name`, `base`, `rate`, `amount`,
`account_id`, and `is_reverse_charge`. Operators (and future invoice
creation flows) can use this to preview compound + reverse-charge
treatment before posting.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `profile_id` | query | string(uuid) | ✓ |  |
| `subtotal` | query | number \| string | ✓ |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/tax/profiles` — List tax profiles

_operationId:_ `list_tax_profiles_api_v1_tax_profiles_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `is_active` | query | boolean \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`TaxProfileResponse`](#schema-taxprofileresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/tax/profiles` — Create tax profile (admin only)

_operationId:_ `create_tax_profile_api_v1_tax_profiles_post`

**Request body**
- `application/json` → [`TaxProfileCreate`](#schema-taxprofilecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`TaxProfileResponse`](#schema-taxprofileresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /api/v1/tax/profiles/{profile_id}` — Update tax profile (admin only)

_operationId:_ `update_tax_profile_api_v1_tax_profiles__profile_id__put`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `profile_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`TaxProfileUpdate`](#schema-taxprofileupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`TaxProfileResponse`](#schema-taxprofileresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/tax/remittances` — List tax remittances

_operationId:_ `list_tax_remittances_api_v1_tax_remittances_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `tax_profile_id` | query | string(uuid) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`TaxRemittanceResponse`](#schema-taxremittanceresponse)[] | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `POST /api/v1/tax/remittances` — Record tax remittance (admin only)

_operationId:_ `record_tax_remittance_api_v1_tax_remittances_post`

**Request body**
- `application/json` → [`TaxRemittanceCreate`](#schema-taxremittancecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`TaxRemittanceResponse`](#schema-taxremittanceresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/tax/reports/component-breakdown` — Per-component tax breakdown for compound profiles (#329 P2)

_operationId:_ `component_breakdown_report_api_v1_tax_reports_component_breakdown_get`

For each tax profile, sum the period's sale subtotals (taxable base)
and decompose across components. Useful for compound profiles like
QC's GST+QST where remittance forms ask for each component separately.

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `profile_id` | query | string(uuid) \| null |  | Filter to one profile; otherwise all active |
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/tax/reports/liability` — Tax liability report (admin only)

_operationId:_ `tax_liability_report_api_v1_tax_reports_liability_get`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `date_from` | query | string(date) \| null |  |  |
| `date_to` | query | string(date) \| null |  |  |

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`TaxLiabilitySummary`](#schema-taxliabilitysummary) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

---

## Tag: Withholding <a id="tag-withholding"></a>

### `POST /api/v1/withholding/invoices/{invoice_id}/apply-payment-with-withholding` — #263 P2: Apply customer payment with withholding split

_operationId:_ `apply_payment_with_withholding_ep_api_v1_withholding_invoices__invoice_id__apply_payment_with_withholding_post`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `invoice_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ApplyWithholdingRequest`](#schema-applywithholdingrequest)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | any | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /api/v1/withholding/profiles` — List withholding profiles

_operationId:_ `list_profiles_api_v1_withholding_profiles_get`

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProfileResponse`](#schema-profileresponse)[] | Successful Response |

### `POST /api/v1/withholding/profiles` — Create withholding profile

_operationId:_ `create_profile_api_v1_withholding_profiles_post`

**Request body**
- `application/json` → [`ProfileCreate`](#schema-profilecreate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `201` | [`ProfileResponse`](#schema-profileresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PATCH /api/v1/withholding/profiles/{profile_id}` — Update withholding profile

_operationId:_ `update_profile_api_v1_withholding_profiles__profile_id__patch`

**Parameters**
| Name | In | Type | Req | Notes |
|---|---|---|---|---|
| `profile_id` | path | string(uuid) | ✓ |  |

**Request body**
- `application/json` → [`ProfileUpdate`](#schema-profileupdate)
- _required_

**Responses**
| Status | Body | Notes |
|---|---|---|
| `200` | [`ProfileResponse`](#schema-profileresponse) | Successful Response |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
