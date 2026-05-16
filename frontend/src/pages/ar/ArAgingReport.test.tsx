import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ArAgingReportPage } from "@/pages/ar/ArAgingReport";
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
    <MemoryRouter initialEntries={["/reports/ar-aging"]}>
      <AppProviders>
        <Routes>
          <Route path="/reports/ar-aging" element={<ArAgingReportPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<ArAgingReportPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/reports/ar-aging").reply(200, {
      as_of: "2026-05-16T00:00:00Z",
      bucket_labels: ["0-30", "31-60", "61+"],
      grand_total: "300.00",
      grand_total_by_bucket: ["100.00", "100.00", "100.00"],
      rows: [
        {
          customer_id: CUSTOMER_ID,
          customer_number: "CUS-0001",
          display_name: "Acme",
          total_outstanding: "300.00",
          buckets: [
            { label: "0-30", amount: "100.00" },
            { label: "31-60", amount: "100.00" },
            { label: "61+", amount: "100.00" },
          ],
        },
      ],
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders bucketed table and CSV button opens the right URL", async () => {
    const openSpy = vi
      .spyOn(window, "open")
      .mockImplementation(() => null);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Acme")).toBeInTheDocument();
    });
    expect(screen.getByText("0-30")).toBeInTheDocument();
    expect(screen.getByTestId("ar-aging-grand-total")).toHaveTextContent(
      "$300.00",
    );

    screen.getByTestId("ar-aging-csv").click();
    expect(openSpy).toHaveBeenCalledWith(
      "/api/v1/reports/ar-aging?format=csv",
      "_blank",
      "noopener,noreferrer",
    );

    openSpy.mockRestore();
  });
});
