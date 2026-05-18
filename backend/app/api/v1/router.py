"""v1 API router aggregate.

Business endpoints will hang off this router as bounded-context modules
land. The health endpoint is intentionally mounted at the app root by
`app.main` (unversioned infra contract), so it is not included here.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.accounting_periods import router as accounting_periods_router
from app.api.v1.accounts import router as accounts_router
from app.api.v1.admin import admin_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.attachments import router as attachments_router
from app.api.v1.auth import router as auth_router
from app.api.v1.banking import imports_router as bank_imports_router
from app.api.v1.banking import mappings_router as bank_mappings_router
from app.api.v1.banking import match_rules_router as bank_match_rules_router
from app.api.v1.banking import reconciliations_router as bank_reconciliations_router
from app.api.v1.banking import transactions_router as bank_transactions_router
from app.api.v1.banking import transfers_router as inter_account_transfers_router
from app.api.v1.bill_payments import bill_payments_router
from app.api.v1.billable_expenses import router as billable_expenses_router
from app.api.v1.bills import router as bills_router
from app.api.v1.bom import router as bom_router
from app.api.v1.budgets import router as budgets_router
from app.api.v1.cameras import router as cameras_router
from app.api.v1.cost_calc import router as cost_calc_router
from app.api.v1.custom_fields import router as custom_fields_router
from app.api.v1.customers import router as customers_router
from app.api.v1.divisions import router as divisions_router
from app.api.v1.email_messages import router as email_messages_router
from app.api.v1.email_messages import statements_router as statements_router
from app.api.v1.expense_categories import router as expense_categories_router
from app.api.v1.expense_claims import router as expense_claims_router
from app.api.v1.fixed_assets import router as fixed_assets_router
from app.api.v1.form_templates import router as form_templates_router
from app.api.v1.inventory_alerts import router as inventory_alerts_router
from app.api.v1.inventory_locations import router as inventory_locations_router
from app.api.v1.inventory_on_hand import router as inventory_on_hand_router
from app.api.v1.inventory_transactions import router as inventory_transactions_router
from app.api.v1.invoices import router as invoices_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.journal_entries import router as journal_entries_router
from app.api.v1.late_fee_policies import router as late_fee_policies_router
from app.api.v1.materials import router as materials_router
from app.api.v1.notes import router as notes_router
from app.api.v1.payments import (
    credit_notes_router,
    customers_credit_router,
    debit_notes_router,
    payments_router,
)
from app.api.v1.pos import router as pos_router
from app.api.v1.printer_state import router as printer_state_router
from app.api.v1.printers import router as printers_router
from app.api.v1.production_orders import router as production_orders_router
from app.api.v1.products import router as products_router
from app.api.v1.quotes import router as quotes_router
from app.api.v1.rates import router as rates_router
from app.api.v1.recurring_bills import router as recurring_bills_router
from app.api.v1.recurring_invoices import router as recurring_invoices_router
from app.api.v1.refunds import router as refunds_router
from app.api.v1.reports import router as reports_router
from app.api.v1.sales import router as sales_router
from app.api.v1.sales_channels import router as sales_channels_router
from app.api.v1.settings import router as settings_router
from app.api.v1.settlements import router as settlements_router
from app.api.v1.shipments import router as shipments_router
from app.api.v1.shipments import sales_shipments_router
from app.api.v1.supplies import router as supplies_router
from app.api.v1.tax_profiles import router as tax_profiles_router
from app.api.v1.users import router as users_router
from app.api.v1.vendors import router as vendors_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(accounting_periods_router)
api_router.include_router(accounts_router)
api_router.include_router(admin_router)
api_router.include_router(approvals_router)
api_router.include_router(attachments_router)
api_router.include_router(budgets_router)
api_router.include_router(divisions_router)
api_router.include_router(settings_router)
api_router.include_router(users_router)
api_router.include_router(custom_fields_router)
api_router.include_router(customers_router)
api_router.include_router(form_templates_router)
api_router.include_router(inventory_alerts_router)
api_router.include_router(inventory_locations_router)
api_router.include_router(inventory_on_hand_router)
api_router.include_router(inventory_transactions_router)
# Cost-calc router shares the ``/jobs`` prefix but registers a specific
# ``/jobs/calculate`` route. It must be included BEFORE jobs_router so
# the more specific path matches before ``/jobs/{job_id}`` swallows it.
api_router.include_router(cost_calc_router)
api_router.include_router(jobs_router)
api_router.include_router(journal_entries_router)
api_router.include_router(materials_router)
api_router.include_router(notes_router)
api_router.include_router(printers_router)
api_router.include_router(printer_state_router)
api_router.include_router(cameras_router)
api_router.include_router(products_router)
api_router.include_router(production_orders_router)
api_router.include_router(bom_router)
api_router.include_router(rates_router)
api_router.include_router(sales_channels_router)
# sales_shipments_router shares the ``/sales`` prefix and must register
# before ``sales_router`` swallowing ``/sales/{sale_id}/...``. The nested
# POST ``/sales/{sale_id}/shipments`` is more specific than the
# ``GET /sales/{sale_id}`` route, but the registration order keeps
# FastAPI's route resolution unambiguous.
api_router.include_router(sales_shipments_router)
api_router.include_router(sales_router)
api_router.include_router(refunds_router)
api_router.include_router(pos_router)
api_router.include_router(quotes_router)
api_router.include_router(invoices_router)
api_router.include_router(bills_router)
api_router.include_router(bill_payments_router)
api_router.include_router(payments_router)
api_router.include_router(credit_notes_router)
api_router.include_router(debit_notes_router)
# Customer-credit-balance read endpoint shares the /customers prefix
# with the main customers router. Register before the bulkier customers
# router so FastAPI matches the more specific /credit-balance route
# first (the existing customers_router was already included earlier in
# this file).
api_router.include_router(customers_credit_router)
api_router.include_router(recurring_invoices_router)
api_router.include_router(recurring_bills_router)
api_router.include_router(late_fee_policies_router)
api_router.include_router(reports_router)
api_router.include_router(shipments_router)
api_router.include_router(supplies_router)
# The statements router lives under /customers but is mounted last so
# /customers/{id} (from customers_router) still wins for ID-only paths.
api_router.include_router(statements_router)
api_router.include_router(email_messages_router)
api_router.include_router(vendors_router)
api_router.include_router(expense_categories_router)
api_router.include_router(expense_claims_router)
api_router.include_router(billable_expenses_router)
api_router.include_router(bank_mappings_router)
api_router.include_router(bank_imports_router)
api_router.include_router(bank_transactions_router)
api_router.include_router(bank_match_rules_router)
api_router.include_router(bank_reconciliations_router)
api_router.include_router(inter_account_transfers_router)
api_router.include_router(fixed_assets_router)
api_router.include_router(settlements_router)
api_router.include_router(tax_profiles_router)
