"""Shared helpers for banking / bank-import tests (Phase 8.9, #136)."""

from __future__ import annotations

import uuid

from app.models.account import Account
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def seed_bank_account(
    session: AsyncSession,
    *,
    code: str = "1010",
    name: str = "Operating Bank",
) -> Account:
    acct = Account(id=uuid.uuid4(), code=code, name=name, type="asset")
    session.add(acct)
    await session.commit()
    return acct


def sample_csv_signed_amount() -> bytes:
    """A Wells-Fargo-like statement: one signed Amount column.
    Positive = deposit, negative = withdrawal."""
    rows = [
        "Date,Description,Amount,Balance",
        "2026-04-01,OPENING BALANCE,0.00,1000.00",
        "2026-04-03,COFFEE SHOP,-4.50,995.50",
        "2026-04-05,DEPOSIT PAYROLL,2500.00,3495.50",
        "2026-04-08,RENT,-1200.00,2295.50",
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def sample_csv_debit_credit() -> bytes:
    """A Chase-like statement: separate Debit and Credit columns."""
    rows = [
        "Date,Description,Debit,Credit",
        "04/01/2026,Opening,,0.00",
        "04/02/2026,GROCERY,52.10,",
        "04/03/2026,REFUND,,18.99",
        "04/04/2026,UTILITIES,135.00,",
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def sample_csv_inflow_outflow() -> bytes:
    """A BofA-like statement: separate Inflow/Outflow columns."""
    rows = [
        "Date,Description,Inflow,Outflow",
        "2026-04-01,GAS STATION,,42.50",
        "2026-04-02,CHECK DEPOSIT,500.00,",
        "2026-04-03,RESTAURANT,,28.75",
    ]
    return ("\n".join(rows) + "\n").encode("utf-8")


def sample_ofx_bytes() -> bytes:
    """A minimal OFX with two STMTTRN entries."""
    body = """OFXHEADER:100
DATA:OFXSGML
<OFX>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<BANKTRANLIST>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260403120000
<TRNAMT>-4.50
<FITID>FIT0001
<NAME>COFFEE SHOP
<MEMO>downtown
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20260405000000
<TRNAMT>2500.00
<FITID>FIT0002
<NAME>PAYROLL
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""
    return body.encode("utf-8")
