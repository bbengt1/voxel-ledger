"""Pydantic schemas for payments + credit/debit notes (Phase 7.4, #112)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PaymentMethodLiteral = Literal["cash", "check", "ach", "wire", "card", "marketplace", "other"]
PaymentStateLiteral = Literal["pending", "applied", "cancelled", "bounced"]
NoteStateLiteral = Literal["draft", "issued", "applied", "cancelled"]


# --- Payments ---------------------------------------------------------------


class PaymentCreate(BaseModel):
    customer_id: uuid.UUID
    amount: Decimal
    method: PaymentMethodLiteral
    reference: str | None = Field(default=None, max_length=128)
    received_at: datetime | None = None
    notes: str | None = None
    # Parity #235: when True, the apply-payment JE debits the
    # undeposited-funds clearing account instead of the bank.
    deposit_to_undeposited: bool = False


class PaymentApplicationInput(BaseModel):
    invoice_id: uuid.UUID
    amount: Decimal


class PaymentApplyRequest(BaseModel):
    applications: list[PaymentApplicationInput] = Field(default_factory=list)
    apply_excess_to_credit: bool = False


class PaymentApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    amount: Decimal
    applied_at: datetime


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payment_number: str
    customer_id: uuid.UUID
    received_at: datetime
    method: PaymentMethodLiteral
    reference: str | None = None
    amount: Decimal
    state: PaymentStateLiteral
    notes: str | None = None
    posting_journal_entry_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    applications: list[PaymentApplicationResponse] = Field(default_factory=list)


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]


class PaymentTransitionRequest(BaseModel):
    note: str | None = None


# --- Credit / Debit notes ---------------------------------------------------


class CreditNoteCreate(BaseModel):
    invoice_id: uuid.UUID
    total_amount: Decimal
    reason: str = ""
    notes: str | None = None


class CreditNoteUpdate(BaseModel):
    total_amount: Decimal | None = None
    reason: str | None = None
    notes: str | None = None


class CreditNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    credit_note_number: str
    customer_id: uuid.UUID
    invoice_id: uuid.UUID
    reason: str
    total_amount: Decimal
    state: NoteStateLiteral
    notes: str | None = None
    posting_journal_entry_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CreditNoteListResponse(BaseModel):
    items: list[CreditNoteResponse]


class DebitNoteCreate(BaseModel):
    invoice_id: uuid.UUID
    total_amount: Decimal
    reason: str = ""
    notes: str | None = None


class DebitNoteUpdate(BaseModel):
    total_amount: Decimal | None = None
    reason: str | None = None
    notes: str | None = None


class DebitNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    debit_note_number: str
    customer_id: uuid.UUID
    invoice_id: uuid.UUID
    reason: str
    total_amount: Decimal
    state: NoteStateLiteral
    notes: str | None = None
    posting_journal_entry_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class DebitNoteListResponse(BaseModel):
    items: list[DebitNoteResponse]


# --- Customer credit balance ------------------------------------------------


class CustomerCreditBalanceResponse(BaseModel):
    customer_id: uuid.UUID
    available_amount: Decimal
    updated_at: datetime | None = None
