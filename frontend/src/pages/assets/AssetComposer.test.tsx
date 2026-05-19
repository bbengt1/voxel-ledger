import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { AssetComposerPage } from "@/pages/assets/AssetComposer";
import { useAuthStore } from "@/store/useAuthStore";

const ASSET_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/assets/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/assets/new" element={<AssetComposerPage />} />
          <Route path="/assets/:id" element={<div>asset-detail</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<AssetComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounts").reply(200, {
      items: [
        { id: "acc-asset", code: "1500", name: "Equipment", type: "asset", is_archived: false },
        {
          id: "acc-accum",
          code: "1599",
          name: "Accumulated Depreciation",
          type: "asset",
          is_archived: false,
        },
        {
          id: "acc-dep-exp",
          code: "6100",
          name: "Depreciation Expense",
          type: "expense",
          is_archived: false,
        },
        { id: "acc-bank", code: "1000", name: "Bank", type: "asset", is_archived: false },
      ],
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("posts an acquire request with the form fields", async () => {
    const user = userEvent.setup();
    let body: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/fixed-assets").reply((config) => {
      body = JSON.parse(config.data as string);
      return [201, { id: ASSET_ID }];
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("picker-asset")).toBeInTheDocument(),
    );

    await user.type(screen.getByTestId("asset-name"), "MacBook Pro");
    await user.type(screen.getByTestId("asset-cost"), "2500.00");
    await user.selectOptions(screen.getByTestId("picker-asset"), "acc-asset");
    await user.selectOptions(screen.getByTestId("picker-accum"), "acc-accum");
    await user.selectOptions(screen.getByTestId("picker-dep-exp"), "acc-dep-exp");
    await user.selectOptions(screen.getByTestId("picker-contra"), "acc-bank");

    await user.click(screen.getByTestId("asset-submit"));

    await waitFor(() => expect(body).toBeDefined());
    expect(body?.["name"]).toBe("MacBook Pro");
    expect(body?.["acquisition_cost"]).toBe("2500.00");
    expect(body?.["asset_account_id"]).toBe("acc-asset");
    expect(body?.["accumulated_depreciation_account_id"]).toBe("acc-accum");
    expect(body?.["depreciation_expense_account_id"]).toBe("acc-dep-exp");
    expect(body?.["contra_account_id"]).toBe("acc-bank");
    expect(body?.["depreciation_method"]).toBe("straight_line");
  });
});
