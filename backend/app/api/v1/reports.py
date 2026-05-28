"""Reporting API (Phase 7.6, #114).

Currently exposes the AR aging report. JSON by default, CSV via
``?format=csv``.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.ap_aging import (
    ApAgingBucketResponse,
    ApAgingReportResponse,
    ApAgingRowResponse,
)
from app.schemas.balance_sheet import (
    BalanceSheetResponse,
    BalanceSheetRowResponse,
)
from app.schemas.budget_variance import (
    BudgetVarianceResponse,
    BudgetVarianceRowResponse,
)
from app.schemas.cash_flow import (
    CashFlowLineResponse,
    CashFlowResponse,
)
from app.schemas.divisions_comparison import (
    ComparisonColumnResponse,
    ComparisonRowResponse,
    DivisionsComparisonResponse,
)
from app.schemas.general_ledger_detail import (
    LedgerDetailResponse,
    LedgerLineResponse,
    LedgerSectionResponse,
)
from app.schemas.income_statement import (
    IncomeStatementResponse,
    IncomeStatementRowResponse,
)
from app.schemas.late_fees import (
    AgingBucketResponse,
    AgingRowResponse,
    ArAgingReportResponse,
)
from app.schemas.sales_inventory_reports import (
    InventoryValuationResponse,
    InventoryValuationRowResponse,
    SalesByPeriodResponse,
    SalesByPeriodRowResponse,
)
from app.schemas.tax_remittances import (
    TaxLiabilityReportResponse,
    TaxLiabilityRowResponse,
)
from app.schemas.trial_balance import (
    TrialBalanceResponse,
    TrialBalanceRowResponse,
)
from app.services.reports import ap_aging as ap_aging_service
from app.services.reports import ar_aging as ar_aging_service
from app.services.reports import balance_sheet as balance_sheet_service
from app.services.reports import budget_variance as budget_variance_service
from app.services.reports import cash_flow as cash_flow_service
from app.services.reports import divisions_comparison as divisions_comparison_service
from app.services.reports import general_ledger_detail as gl_detail_service
from app.services.reports import income_statement as income_statement_service
from app.services.reports import inventory_valuation as inventory_valuation_service
from app.services.reports import sales_by_period as sales_by_period_service
from app.services.reports import tax_liability as tax_liability_service
from app.services.reports import trial_balance as trial_balance_service

router = APIRouter(prefix="/reports", tags=["reports"])

_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _parse_buckets(raw: str | None) -> list[int] | None:
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        cuts = [int(p) for p in parts]
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="buckets must be a comma-separated list of integers (e.g. 30,60,90)",
        ) from exc
    if any(c <= 0 for c in cuts):
        raise HTTPException(status_code=400, detail="bucket cut points must be > 0")
    return cuts


@router.get("/ar-aging", response_model=ArAgingReportResponse)
async def ar_aging_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    buckets: Annotated[str | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    cuts = _parse_buckets(buckets)
    report = await ar_aging_service.build(session, buckets=cuts)

    if format == "csv":
        body = ar_aging_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="ar-aging.csv"'},
        )

    return ArAgingReportResponse(
        as_of=report.as_of,
        bucket_labels=report.bucket_labels,
        rows=[
            AgingRowResponse(
                customer_id=row.customer_id,
                customer_number=row.customer_number,
                display_name=row.display_name,
                total_outstanding=row.total_outstanding,
                buckets=[AgingBucketResponse(label=b.label, amount=b.amount) for b in row.buckets],
            )
            for row in report.rows
        ],
        grand_total=report.grand_total,
        grand_total_by_bucket=report.grand_total_by_bucket,
    )  # type: ignore[return-value]


@router.get("/ap-aging", response_model=ApAgingReportResponse)
async def ap_aging_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    buckets: Annotated[str | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    cuts = _parse_buckets(buckets)
    report = await ap_aging_service.build(session, buckets=cuts)

    if format == "csv":
        body = ap_aging_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="ap-aging.csv"'},
        )

    return ApAgingReportResponse(
        as_of=report.as_of,
        bucket_labels=report.bucket_labels,
        rows=[
            ApAgingRowResponse(
                vendor_id=row.vendor_id,
                vendor_number=row.vendor_number,
                display_name=row.display_name,
                total_outstanding=row.total_outstanding,
                buckets=[
                    ApAgingBucketResponse(label=b.label, amount=b.amount) for b in row.buckets
                ],
            )
            for row in report.rows
        ],
        grand_total=report.grand_total,
        grand_total_by_bucket=report.grand_total_by_bucket,
    )  # type: ignore[return-value]


@router.get("/tax-liability", response_model=TaxLiabilityReportResponse)
async def tax_liability_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    profile_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        report = await tax_liability_service.build(
            session,
            date_from=date_from,
            date_to=date_to,
            profile_id=str(profile_id) if profile_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = tax_liability_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="tax-liability.csv"'},
        )

    return TaxLiabilityReportResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        rows=[
            TaxLiabilityRowResponse(
                profile_id=uuid.UUID(row.profile_id),
                profile_code=row.profile_code,
                profile_name=row.profile_name,
                jurisdiction=row.jurisdiction,
                rate_id=uuid.UUID(row.rate_id),
                rate_name=row.rate_name,
                rate=row.rate,
                compound_on_previous=row.compound_on_previous,
                tax_collected=row.tax_collected,
                tax_remitted=row.tax_remitted,
                net_liability=row.net_liability,
                gross_taxable_sales=row.gross_taxable_sales,
            )
            for row in report.rows
        ],
        grand_total_collected=report.grand_total_collected,
        grand_total_remitted=report.grand_total_remitted,
        grand_total_net=report.grand_total_net,
    )  # type: ignore[return-value]


@router.get("/income-statement", response_model=IncomeStatementResponse)
async def income_statement_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    division_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        report = await income_statement_service.build(
            session,
            date_from=date_from,
            date_to=date_to,
            division_id=division_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = income_statement_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="income-statement.csv"',
            },
        )

    def _to_rows(rows):
        return [
            IncomeStatementRowResponse(
                account_id=uuid.UUID(r.account_id),
                code=r.code,
                name=r.name,
                depth=r.depth,
                section=r.section,
                amount=r.amount,
            )
            for r in rows
        ]

    return IncomeStatementResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        division_id=uuid.UUID(report.division_id) if report.division_id else None,
        revenue_rows=_to_rows(report.revenue_rows),
        cogs_rows=_to_rows(report.cogs_rows),
        operating_expense_rows=_to_rows(report.operating_expense_rows),
        total_revenue=report.total_revenue,
        total_cogs=report.total_cogs,
        gross_profit=report.gross_profit,
        total_operating_expenses=report.total_operating_expenses,
        operating_income=report.operating_income,
        net_income=report.net_income,
    )  # type: ignore[return-value]


@router.get("/balance-sheet", response_model=BalanceSheetResponse)
async def balance_sheet_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    as_of: Annotated[date_type, Query(...)],
    division_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    report = await balance_sheet_service.build(session, as_of=as_of, division_id=division_id)

    if format == "csv":
        body = balance_sheet_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="balance-sheet.csv"'},
        )

    def _to_rows(rows):
        return [
            BalanceSheetRowResponse(
                account_id=uuid.UUID(r.account_id),
                code=r.code,
                name=r.name,
                depth=r.depth,
                section=r.section,
                balance=r.balance,
            )
            for r in rows
        ]

    return BalanceSheetResponse(
        as_of=report.as_of,
        division_id=uuid.UUID(report.division_id) if report.division_id else None,
        asset_rows=_to_rows(report.asset_rows),
        liability_rows=_to_rows(report.liability_rows),
        equity_rows=_to_rows(report.equity_rows),
        total_assets=report.total_assets,
        total_liabilities=report.total_liabilities,
        total_equity=report.total_equity,
        total_liabilities_and_equity=report.total_liabilities_and_equity,
        imbalance=report.imbalance,
    )  # type: ignore[return-value]


_CASH_FLOW_READ_ROLES = ("owner", "bookkeeper", "viewer")


@router.get("/cash-flow", response_model=CashFlowResponse)
async def cash_flow_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_CASH_FLOW_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    division_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        report = await cash_flow_service.build(
            session,
            date_from=date_from,
            date_to=date_to,
            division_id=division_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = cash_flow_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="cash-flow.csv"'},
        )

    def _to_lines(lines):
        return [
            CashFlowLineResponse(
                section=line.section,
                line_item=line.line_item,
                amount=line.amount,
            )
            for line in lines
        ]

    return CashFlowResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        division_id=uuid.UUID(report.division_id) if report.division_id else None,
        operating_lines=_to_lines(report.operating_lines),
        operating_total=report.operating_total,
        investing_lines=_to_lines(report.investing_lines),
        investing_total=report.investing_total,
        financing_lines=_to_lines(report.financing_lines),
        financing_total=report.financing_total,
        net_change_in_cash=report.net_change_in_cash,
        reconciliation_residual=report.reconciliation_residual,
    )  # type: ignore[return-value]


@router.get("/trial-balance", response_model=TrialBalanceResponse)
async def trial_balance_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    division_id: Annotated[uuid.UUID | None, Query()] = None,
    include_zero: Annotated[bool, Query()] = False,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        report = await trial_balance_service.build(
            session,
            date_from=date_from,
            date_to=date_to,
            division_id=division_id,
            include_zero=include_zero,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = trial_balance_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="trial-balance.csv"'},
        )

    return TrialBalanceResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        division_id=uuid.UUID(report.division_id) if report.division_id else None,
        include_zero=report.include_zero,
        rows=[
            TrialBalanceRowResponse(
                account_id=uuid.UUID(r.account_id),
                code=r.code,
                name=r.name,
                type=r.type,
                opening_balance=r.opening_balance,
                period_debit=r.period_debit,
                period_credit=r.period_credit,
                closing_balance=r.closing_balance,
            )
            for r in report.rows
        ],
        total_period_debit=report.total_period_debit,
        total_period_credit=report.total_period_credit,
    )  # type: ignore[return-value]


@router.get("/general-ledger-detail", response_model=LedgerDetailResponse)
async def general_ledger_detail_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    division_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    """Per-account drill-down behind the trial balance.

    Returns one section per touched account (or just the
    ``account_id``-filtered one) with opening balance + every JE
    line in the window + running balance + closing balance. CSV
    export via ``?format=csv``.
    """
    try:
        report = await gl_detail_service.build(
            session,
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            division_id=division_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = gl_detail_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": ('attachment; filename="general-ledger-detail.csv"')},
        )

    return LedgerDetailResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        account_id=uuid.UUID(report.account_id) if report.account_id else None,
        division_id=uuid.UUID(report.division_id) if report.division_id else None,
        sections=[
            LedgerSectionResponse(
                account_id=uuid.UUID(s.account_id),
                code=s.code,
                name=s.name,
                type=s.type,
                opening_balance=s.opening_balance,
                closing_balance=s.closing_balance,
                period_debit=s.period_debit,
                period_credit=s.period_credit,
                lines=[
                    LedgerLineResponse(
                        journal_entry_id=uuid.UUID(line.journal_entry_id),
                        entry_number=line.entry_number,
                        posted_at=line.posted_at,
                        description=line.description,
                        debit=line.debit,
                        credit=line.credit,
                        running_balance=line.running_balance,
                    )
                    for line in s.lines
                ],
            )
            for s in report.sections
        ],
    )  # type: ignore[return-value]


@router.get(
    "/divisions-comparison",
    response_model=DivisionsComparisonResponse,
)
async def divisions_comparison_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    format: Annotated[str | None, Query()] = None,
) -> Response:
    """Per-division income statement side-by-side (Parity #229).

    Every non-archived division gets its own column; lines without
    a division contribute to a final ``(unallocated)`` column. CSV
    export mirrors the table's column shape.
    """
    try:
        report = await divisions_comparison_service.build(
            session, date_from=date_from, date_to=date_to
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = divisions_comparison_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": ('attachment; filename="divisions-comparison.csv"')},
        )

    def _row(r) -> ComparisonRowResponse:
        return ComparisonRowResponse(
            account_id=r.account_id,
            code=r.code,
            name=r.name,
            section=r.section,
            amounts=r.amounts,
        )

    return DivisionsComparisonResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        columns=[
            ComparisonColumnResponse(division_id=c.division_id, code=c.code, label=c.label)
            for c in report.columns
        ],
        revenue_rows=[_row(r) for r in report.revenue_rows],
        cogs_rows=[_row(r) for r in report.cogs_rows],
        operating_expense_rows=[_row(r) for r in report.operating_expense_rows],
        total_revenue=report.total_revenue,
        total_cogs=report.total_cogs,
        gross_profit=report.gross_profit,
        total_operating_expenses=report.total_operating_expenses,
        operating_income=report.operating_income,
        net_income=report.net_income,
    )  # type: ignore[return-value]


@router.get("/budget-variance", response_model=BudgetVarianceResponse)
async def budget_variance_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    period_id: Annotated[uuid.UUID, Query(...)],
    division_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    """Budget vs actual variance for an ``accounting_period`` (Parity
    #227). When ``division_id`` is set, both sides are filtered to
    that division."""
    try:
        report = await budget_variance_service.build(
            session, period_id=period_id, division_id=division_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = budget_variance_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={"Content-Disposition": ('attachment; filename="budget-variance.csv"')},
        )

    def _row(r) -> BudgetVarianceRowResponse:
        return BudgetVarianceRowResponse(
            account_id=uuid.UUID(r.account_id),
            code=r.code,
            name=r.name,
            section=r.section,
            budget=r.budget,
            actual=r.actual,
            variance=r.variance,
            variance_pct=r.variance_pct,
        )

    return BudgetVarianceResponse(
        period_id=uuid.UUID(report.period_id),
        period_name=report.period_name,
        date_from=report.date_from,
        date_to=report.date_to,
        division_id=uuid.UUID(report.division_id) if report.division_id else None,
        revenue_rows=[_row(r) for r in report.revenue_rows],
        cogs_rows=[_row(r) for r in report.cogs_rows],
        operating_expense_rows=[_row(r) for r in report.operating_expense_rows],
        total_revenue_budget=report.total_revenue_budget,
        total_revenue_actual=report.total_revenue_actual,
        total_cogs_budget=report.total_cogs_budget,
        total_cogs_actual=report.total_cogs_actual,
        total_operating_expense_budget=report.total_operating_expense_budget,
        total_operating_expense_actual=report.total_operating_expense_actual,
    )  # type: ignore[return-value]


_INVENTORY_READ_ROLES = ("owner", "bookkeeper", "production", "viewer")


@router.get("/sales-by-period", response_model=SalesByPeriodResponse)
async def sales_by_period_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    date_from: Annotated[date_type, Query(...)],
    date_to: Annotated[date_type, Query(...)],
    bucket: Annotated[str, Query()] = "month",
    channel_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    try:
        report = await sales_by_period_service.build(
            session,
            date_from=date_from,
            date_to=date_to,
            bucket=bucket,  # type: ignore[arg-type]
            channel_id=channel_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    if format == "csv":
        body = sales_by_period_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="sales-by-period.csv"',
            },
        )

    return SalesByPeriodResponse(
        date_from=report.date_from,
        date_to=report.date_to,
        bucket=report.bucket,
        channel_id=uuid.UUID(report.channel_id) if report.channel_id else None,
        rows=[
            SalesByPeriodRowResponse(
                channel_id=uuid.UUID(r.channel_id),
                bucket_start=r.bucket_start,
                gross_sales=r.gross_sales,
                refunds=r.refunds,
                net_sales=r.net_sales,
                order_count=r.order_count,
            )
            for r in report.rows
        ],
        total_gross=report.total_gross,
        total_refunds=report.total_refunds,
        total_net=report.total_net,
        total_orders=report.total_orders,
    )  # type: ignore[return-value]


@router.get("/inventory-valuation", response_model=InventoryValuationResponse)
async def inventory_valuation_report(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_INVENTORY_READ_ROLES))],
    as_of: Annotated[date_type | None, Query()] = None,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
    format: Annotated[str | None, Query()] = None,
) -> Response:
    report = await inventory_valuation_service.build(session, as_of=as_of, location_id=location_id)

    if format == "csv":
        body = inventory_valuation_service.to_csv(report)
        return PlainTextResponse(
            content=body,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="inventory-valuation.csv"',
            },
        )

    return InventoryValuationResponse(
        as_of=report.as_of,
        location_id=uuid.UUID(report.location_id) if report.location_id else None,
        rows=[
            InventoryValuationRowResponse(
                entity_kind=r.entity_kind,
                entity_id=uuid.UUID(r.entity_id),
                name=r.name,
                sku=r.sku,
                location_id=uuid.UUID(r.location_id),
                location_name=r.location_name,
                on_hand=r.on_hand,
                unit_cost=r.unit_cost,
                valuation=r.valuation,
            )
            for r in report.rows
        ],
        total_valuation=report.total_valuation,
        totals_by_kind=report.totals_by_kind,
        totals_by_location=report.totals_by_location,
    )  # type: ignore[return-value]
