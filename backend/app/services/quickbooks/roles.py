"""Posting-line account ROLES the QBO account map must cover (#315, epic #312).

Derived from every local GL posting site (cogs/sales, invoices, payments, bills,
bill-payments, credit/debit notes, depreciation, fixed assets + disposals, tax
remittances, expense claims, transfers, deposit slips, settlement matcher). When
QBO becomes the system of record (Phase 3), each journal line resolves its
account through :class:`app.services.quickbooks.account_map` keyed by one of
these roles. The account map is a hard prerequisite for Phase 3.
"""

from __future__ import annotations

import enum


class QBOAccountRole(enum.StrEnum):
    # Sales / AR
    REVENUE = "revenue"
    ACCOUNTS_RECEIVABLE = "accounts_receivable"
    SALES_TAX_PAYABLE = "sales_tax_payable"
    LATE_FEE_INCOME = "late_fee_income"
    BAD_DEBT = "bad_debt"
    # COGS / inventory
    COGS = "cogs"
    INVENTORY = "inventory"
    # Cash / clearing
    BANK = "bank"
    UNDEPOSITED_FUNDS = "undeposited_funds"
    # AP / expenses
    ACCOUNTS_PAYABLE = "accounts_payable"
    EXPENSE = "expense"
    TAX_EXPENSE = "tax_expense"
    EMPLOYEE_REIMBURSABLE = "employee_reimbursable"
    # Fixed assets
    FIXED_ASSET = "fixed_asset"
    DEPRECIATION_EXPENSE = "depreciation_expense"
    ACCUMULATED_DEPRECIATION = "accumulated_depreciation"
    DISPOSAL_PROCEEDS = "disposal_proceeds"
    GAIN_LOSS_ON_DISPOSAL = "gain_loss_on_disposal"
    # Tax
    TAX_LIABILITY = "tax_liability"
    # Marketplace settlement
    MARKETPLACE_CLEARING = "marketplace_clearing"
    MARKETPLACE_FEE = "marketplace_fee"
    PAYOUT = "payout"
    SETTLEMENT_ADJUSTMENT = "settlement_adjustment"


QBO_ACCOUNT_ROLE_VALUES: tuple[str, ...] = tuple(r.value for r in QBOAccountRole)
