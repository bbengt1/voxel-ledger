import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { CustomerComposerPage } from "@/pages/ar/CustomerComposer";
import { useAuthStore } from "@/store/useAuthStore";

const CUSTOMER_ID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/customers/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/customers/new" element={<CustomerComposerPage />} />
          <Route path="/customers/:id" element={<div>customer-detail</div>} />
          <Route path="/customers" element={<div>customers-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<CustomerComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounts").reply(200, { items: [] });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("creates a customer with two contacts and marks one primary", async () => {
    const user = userEvent.setup();
    let postBody: Record<string, unknown> | undefined;
    const contactBodies: Array<Record<string, unknown>> = [];
    mock.onPost("/api/v1/customers").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: CUSTOMER_ID,
          customer_number: "CUS-0001",
          display_name: postBody?.["display_name"],
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
      ];
    });
    mock.onPost(`/api/v1/customers/${CUSTOMER_ID}/contacts`).reply((config) => {
      contactBodies.push(JSON.parse(config.data as string));
      return [201, { id: "c1" }];
    });

    renderPage();

    await user.type(
      screen.getByTestId("customer-display-name"),
      "Acme Co",
    );

    await user.click(screen.getByTestId("add-contact-btn"));
    await user.click(screen.getByTestId("add-contact-btn"));

    await user.type(screen.getByTestId("contact-0-name"), "Alice");
    await user.type(screen.getByTestId("contact-1-name"), "Bob");
    await user.click(screen.getByTestId("contact-1-primary"));

    await user.click(screen.getByTestId("customer-save"));

    await waitFor(() => {
      expect(postBody).toBeDefined();
    });
    expect(postBody?.["display_name"]).toBe("Acme Co");

    await waitFor(() => {
      expect(contactBodies).toHaveLength(2);
    });
    expect(contactBodies[0]?.["name"]).toBe("Alice");
    expect(contactBodies[0]?.["is_primary"]).toBe(false);
    expect(contactBodies[1]?.["name"]).toBe("Bob");
    expect(contactBodies[1]?.["is_primary"]).toBe(true);
  });
});
