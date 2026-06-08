#!/usr/bin/env python3
"""
QuickBooks Online — Phase 0 sandbox spike (DISPOSABLE — not application code).

Tracks #313 / epic #312. This is a throwaway script to prove the auth-code flow,
realmId capture, and a Customer + JournalEntry round-trip against a SANDBOX company,
and to confirm `intuit-oauth` imports on Python 3.13. Do NOT import this from the app;
the real integration lives under app/services/quickbooks/ in Phases 1-3.

Per the Phase-0 findings (docs/quickbooks_phase0_findings.md):
  - OAuth via `intuit-oauth` (intuitlib); API calls via raw httpx.
  - minorversion = 75; idempotency via a `requestid` UUID per write.
  - Sandbox base URL: https://sandbox-quickbooks.api.intuit.com

Setup (one-time):
  python3.13 -m venv /tmp/qbo-spike && . /tmp/qbo-spike/bin/activate
  pip install "intuit-oauth==1.2.6" "httpx>=0.27"
  export QBO_CLIENT_ID=...        # sandbox keys from developer.intuit.com
  export QBO_CLIENT_SECRET=...
  export QBO_REDIRECT_URI="http://localhost:8000/callback"   # must match the app's redirect URI exactly

Run:
  python docs/spikes/quickbooks_spike.py
  # 1) open the printed URL, authorize the sandbox company
  # 2) paste the full redirected URL (contains ?code=...&realmId=...) back into the prompt

Record the result in docs/quickbooks_phase0_findings.md §9 and delete the venv.
"""
from __future__ import annotations

import os
import sys
import uuid
from urllib.parse import parse_qs, urlparse

import httpx

try:
    from intuitlib.client import AuthClient
    from intuitlib.enums import Scopes
except ImportError:
    sys.exit("pip install 'intuit-oauth==1.2.6' httpx  (in a Python 3.13 venv)")

SANDBOX_BASE = "https://sandbox-quickbooks.api.intuit.com"
MINORVERSION = 75


def _env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"missing env var {name} (see the setup block in this file)")
    return val


def main() -> int:
    print(f"intuit-oauth OK on Python {sys.version.split()[0]}")  # 3.13 import check

    auth_client = AuthClient(
        client_id=_env("QBO_CLIENT_ID"),
        client_secret=_env("QBO_CLIENT_SECRET"),
        environment="sandbox",
        redirect_uri=_env("QBO_REDIRECT_URI"),
    )

    # --- Step 1: authorization URL (CSRF state included by the lib) ---
    auth_url = auth_client.get_authorization_url([Scopes.ACCOUNTING])
    print("\n1) Open this URL, authorize the SANDBOX company, then copy the URL you land on:\n")
    print(f"   {auth_url}\n")
    redirected = input("2) Paste the full redirected URL here:\n   ").strip()

    qs = parse_qs(urlparse(redirected).query)
    code = qs.get("code", [None])[0]
    realm_id = qs.get("realmId", [None])[0]
    if not code or not realm_id:
        sys.exit("could not parse ?code= and ?realmId= from the pasted URL")
    print(f"   captured realmId={realm_id}")

    # --- Step 2: exchange code -> tokens (note token fields per findings §1) ---
    auth_client.get_bearer_token(code, realm_id=realm_id)
    print(
        "3) tokens acquired:"
        f"\n   access_token_expires_in≈3600s"
        f"\n   refresh_token (persist the latest value on every refresh!): "
        f"{auth_client.refresh_token[:8]}…"
    )

    headers = {
        "Authorization": f"Bearer {auth_client.access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    base = f"{SANDBOX_BASE}/v3/company/{realm_id}"

    with httpx.Client(headers=headers, timeout=30) as http:
        # --- Step 3: read CompanyInfo ---
        r = http.get(f"{base}/companyinfo/{realm_id}", params={"minorversion": MINORVERSION})
        r.raise_for_status()
        name = r.json()["CompanyInfo"]["CompanyName"]
        print(f"4) CompanyInfo OK — company name: {name!r}")

        # --- Step 4: create + read a Customer (idempotent via requestid) ---
        cust_req_id = str(uuid.uuid4())
        disp = f"Phase0 Spike {cust_req_id[:8]}"
        r = http.post(
            f"{base}/customer",
            params={"minorversion": MINORVERSION, "requestid": cust_req_id},
            json={"DisplayName": disp},
        )
        r.raise_for_status()
        cust = r.json()["Customer"]
        print(f"5) Customer created — Id={cust['Id']} SyncToken={cust['SyncToken']} ({disp})")

        # --- Step 5: create a balanced JournalEntry (findings §4) ---
        # Two non-AR/AP accounts so we don't need an Entity ref. Replace the
        # AccountRef ids with real sandbox account ids (GET {base}/query?query=select * from Account).
        acct = http.get(
            f"{base}/query",
            params={"minorversion": MINORVERSION, "query": "select Id from Account maxresults 2"},
        ).json()["QueryResponse"]["Account"]
        if len(acct) < 2:
            print("   (skip JE — sandbox has <2 accounts to post between)")
        else:
            a, b = acct[0]["Id"], acct[1]["Id"]
            je_req_id = str(uuid.uuid4())
            je = {
                "Line": [
                    {
                        "DetailType": "JournalEntryLineDetail",
                        "Amount": 1.00,
                        "JournalEntryLineDetail": {"PostingType": "Debit", "AccountRef": {"value": a}},
                    },
                    {
                        "DetailType": "JournalEntryLineDetail",
                        "Amount": 1.00,
                        "JournalEntryLineDetail": {"PostingType": "Credit", "AccountRef": {"value": b}},
                    },
                ]
            }
            r = http.post(
                f"{base}/journalentry",
                params={"minorversion": MINORVERSION, "requestid": je_req_id},
                json=je,
            )
            r.raise_for_status()
            jid = r.json()["JournalEntry"]["Id"]
            print(f"6) JournalEntry created — Id={jid} (balanced $1.00 debit/credit)")

    print("\nSPIKE PASSED — record the result in docs/quickbooks_phase0_findings.md §9.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
