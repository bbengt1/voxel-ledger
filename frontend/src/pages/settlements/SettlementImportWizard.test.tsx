import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SettlementImportWizardPage } from "@/pages/settlements/SettlementImportWizard";
import { useAuthStore } from "@/store/useAuthStore";

const SETTLEMENT_ID = "ssssssss-ssss-ssss-ssss-ssssssssssss";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/settlements/import"]}>
      <AppProviders>
        <Routes>
          <Route path="/settlements/import" element={<SettlementImportWizardPage />} />
          <Route path="/settlements/:id" element={<div>settlement-board</div>} />
          <Route path="/settlements" element={<div>settlements-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<SettlementImportWizardPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/sales-channels").reply(200, {
      items: [
        { id: "chan-1", name: "Etsy Store", slug: "etsy", kind: "marketplace" },
      ],
    });
    mock.onGet("/api/v1/accounts").reply(200, {
      items: [
        { id: "acc-bank", code: "1000", name: "Bank", type: "asset", is_archived: false },
      ],
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("posts multipart/form-data with all form fields", async () => {
    const user = userEvent.setup();
    let requestHeaders: Record<string, string> | undefined;
    let requestBody: FormData | undefined;
    mock.onPost("/api/v1/settlements").reply((config) => {
      requestHeaders = config.headers as Record<string, string>;
      requestBody = config.data as FormData;
      return [201, { id: SETTLEMENT_ID }];
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("import-channel")).toBeInTheDocument(),
    );

    await user.selectOptions(screen.getByTestId("import-channel"), "chan-1");
    await user.selectOptions(screen.getByTestId("import-payout-account"), "acc-bank");

    const file = new File(["Type,Amount\nSale,10.00"], "etsy.csv", {
      type: "text/csv",
    });
    await user.upload(screen.getByTestId("import-file"), file);

    await user.click(screen.getByTestId("import-submit"));

    await waitFor(() => expect(requestBody).toBeDefined());
    expect(requestHeaders?.["Content-Type"]).toMatch(/multipart\/form-data/);
    expect(requestBody?.get("channel_id")).toBe("chan-1");
    expect(requestBody?.get("payout_account_id")).toBe("acc-bank");
    expect(requestBody?.get("format_kind")).toBe("etsy");
    const uploaded = requestBody?.get("file");
    expect(uploaded).toBeInstanceOf(File);
  });
});
