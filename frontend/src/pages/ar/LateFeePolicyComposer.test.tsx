import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { LateFeePolicyComposerPage } from "@/pages/ar/LateFeePolicyComposer";
import { useAuthStore } from "@/store/useAuthStore";

const CUSTOMER_ID = "11111111-1111-1111-1111-111111111111";
const POLICY_ID = "33333333-3333-3333-3333-333333333333";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/late-fee-policies/new"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/late-fee-policies/new"
            element={<LateFeePolicyComposerPage />}
          />
          <Route
            path="/late-fee-policies/:id"
            element={<div>policy-detail</div>}
          />
          <Route
            path="/late-fee-policies"
            element={<div>policies-list</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<LateFeePolicyComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/customers").reply(200, {
      items: [
        {
          id: CUSTOMER_ID,
          customer_number: "CUS-0001",
          display_name: "Acme",
          legal_name: null,
          primary_email: null,
          phone: null,
          payment_terms_days: 30,
          state: "active",
          billing_address: null,
          shipping_address: null,
          default_revenue_account_id: null,
          default_ar_account_id: null,
          tax_profile_id: null,
          notes: null,
          contacts: [],
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  function postReply(returnedCustomerId: string | null) {
    let postBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/late-fee-policies").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: POLICY_ID,
          customer_id: returnedCustomerId,
          kind: "percent_of_outstanding",
          amount: "1.50",
          grace_period_days: 0,
          apply_after_days: 30,
          compound_interval_days: 30,
          is_active: true,
          notes: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });
    return () => postBody;
  }

  it("submits a global policy with customer_id null", async () => {
    const user = userEvent.setup();
    const getBody = postReply(null);

    renderPage();

    expect(screen.getByTestId("scope-global")).toBeChecked();
    await user.clear(screen.getByTestId("policy-amount"));
    await user.type(screen.getByTestId("policy-amount"), "1.5");
    await user.click(screen.getByTestId("save-policy-btn"));

    await waitFor(() => {
      expect(getBody()).toBeDefined();
    });
    const body = getBody();
    expect(body?.["customer_id"]).toBeNull();
    expect(body?.["kind"]).toBe("percent_of_outstanding");
    expect(body?.["amount"]).toBe("1.5");
  });

  it("submits a customer-specific policy with the picked customer_id", async () => {
    const user = userEvent.setup();
    const getBody = postReply(CUSTOMER_ID);

    renderPage();

    await user.click(screen.getByTestId("scope-customer"));
    await user.click(screen.getByTestId("policy-customer-picker-input"));
    await waitFor(() => {
      expect(
        screen.getByTestId(`policy-customer-picker-option-${CUSTOMER_ID}`),
      ).toBeInTheDocument();
    });
    await user.click(
      screen.getByTestId(`policy-customer-picker-option-${CUSTOMER_ID}`),
    );

    await user.selectOptions(screen.getByTestId("policy-kind"), "flat");
    await user.clear(screen.getByTestId("policy-amount"));
    await user.type(screen.getByTestId("policy-amount"), "25");
    await user.click(screen.getByTestId("save-policy-btn"));

    await waitFor(() => {
      expect(getBody()).toBeDefined();
    });
    const body = getBody();
    expect(body?.["customer_id"]).toBe(CUSTOMER_ID);
    expect(body?.["kind"]).toBe("flat");
    expect(body?.["amount"]).toBe("25");
  });
});
