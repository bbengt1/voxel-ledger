import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { AssetDetailPage } from "@/pages/assets/AssetDetail";
import { useAuthStore } from "@/store/useAuthStore";

const ASSET_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function mockAsset(state: "active" | "disposed") {
  return {
    id: ASSET_ID,
    asset_number: "ASSET-0001",
    name: "MacBook Pro",
    kind: "tangible",
    asset_class: "computer",
    acquired_on: "2026-01-01",
    acquisition_cost: "2500.00",
    salvage_value: "0",
    useful_life_months: 36,
    depreciation_method: "straight_line",
    asset_account_id: "acc-asset",
    accumulated_depreciation_account_id: "acc-accum",
    depreciation_expense_account_id: "acc-dep-exp",
    serial_number: null,
    vendor_id: null,
    acquisition_bill_id: null,
    state,
    last_depreciated_on: null,
    posting_journal_entry_id: null,
    notes: null,
    created_by_user_id: "u",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/assets/${ASSET_ID}`]}>
      <AppProviders>
        <Routes>
          <Route path="/assets/:id" element={<AssetDetailPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<AssetDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet(`/api/v1/fixed-assets/${ASSET_ID}/depreciation-schedule`).reply(200, {
      asset_id: ASSET_ID,
      entries: [],
      total_depreciation: "0",
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("disables the Disposal tab when state == disposed", async () => {
    mock.onGet(`/api/v1/fixed-assets/${ASSET_ID}`).reply(200, mockAsset("disposed"));
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("tab-disposal")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("tab-disposal")).toBeDisabled();
  });

  it("shows the disposal form when active", async () => {
    mock.onGet(`/api/v1/fixed-assets/${ASSET_ID}`).reply(200, mockAsset("active"));
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("tab-disposal")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("tab-disposal")).not.toBeDisabled();
  });
});
