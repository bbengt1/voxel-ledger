import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { InvoiceDetailPage } from "@/pages/ar/InvoiceDetail";
import { useAuthStore } from "@/store/useAuthStore";

const INVOICE_ID = "11111111-1111-1111-1111-111111111111";
const CN_ID = "33333333-3333-3333-3333-333333333333";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/invoices/${INVOICE_ID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/invoices/:id" element={<InvoiceDetailPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<InvoiceDetailPage /> credit-note inline composer", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet(`/api/v1/invoices/${INVOICE_ID}`).reply(200, {
      id: INVOICE_ID,
      invoice_number: "INV-2026-0001",
      customer_id: "cust",
      state: "issued",
      currency: "USD",
      subtotal: "100.00",
      discount_amount: "0.00",
      tax_amount: "0.00",
      total_amount: "100.00",
      amount_paid: "0.00",
      amount_outstanding: "100.00",
      items: [],
      notes: null,
      due_at: null,
      issued_at: "2026-05-01T00:00:00Z",
      posting_journal_entry_id: null,
      billing_address_snapshot: null,
      quote_id: null,
      sale_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      created_by_user_id: "u",
    });
    mock.onGet("/api/v1/credit-notes").reply(200, { items: [] });
    mock.onGet("/api/v1/debit-notes").reply(200, { items: [] });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("submits a credit note with the right shape and issues it", async () => {
    const user = userEvent.setup();
    let postBody: Record<string, unknown> | undefined;
    let issued = false;
    mock.onPost("/api/v1/credit-notes").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: CN_ID,
          credit_note_number: "CN-2026-0001",
          customer_id: "cust",
          invoice_id: INVOICE_ID,
          reason: postBody?.["reason"],
          total_amount: postBody?.["total_amount"],
          state: "draft",
          notes: null,
          posting_journal_entry_id: null,
          created_at: "2026-05-01T00:00:00Z",
          updated_at: "2026-05-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });
    mock.onPost(`/api/v1/credit-notes/${CN_ID}/issue`).reply(() => {
      issued = true;
      return [200, {}];
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("action-credit-note")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("action-credit-note"));
    await waitFor(() => {
      expect(screen.getByTestId("credit-note-composer")).toBeInTheDocument();
    });

    await user.type(screen.getByTestId("credit-note-amount"), "25");
    await user.click(screen.getByTestId("credit-note-submit"));

    await waitFor(() => {
      expect(postBody).toBeDefined();
    });
    expect(postBody?.["invoice_id"]).toBe(INVOICE_ID);
    expect(postBody?.["total_amount"]).toBe("25");
    expect(postBody?.["reason"]).toBe("return");

    await waitFor(() => {
      expect(issued).toBe(true);
    });
  });

  it("write-off flow posts to /write-off with the reason (Parity #236)", async () => {
    const user = userEvent.setup();
    let writeOffBody: Record<string, unknown> | undefined;
    mock
      .onPost(`/api/v1/invoices/${INVOICE_ID}/write-off`)
      .reply((config) => {
        writeOffBody = JSON.parse(config.data as string);
        return [200, {}];
      });

    renderPage();

    const action = await screen.findByTestId("action-write-off");
    await user.click(action);

    await waitFor(() => {
      expect(screen.getByTestId("write-off-dialog")).toBeInTheDocument();
    });
    await user.type(screen.getByTestId("write-off-reason"), "customer bankrupt");
    await user.click(screen.getByTestId("action-write-off-confirm"));

    await waitFor(() => expect(writeOffBody).toBeDefined());
    expect(writeOffBody?.["reason"]).toBe("customer bankrupt");
  });
});
