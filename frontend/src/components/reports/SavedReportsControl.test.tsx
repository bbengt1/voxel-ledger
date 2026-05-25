import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { SavedReportsControl } from "@/components/reports/SavedReportsControl";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

describe("<SavedReportsControl />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("posts current filters when Save is clicked", async () => {
    mock.onGet("/api/v1/saved-reports").reply(200, []);
    let posted: unknown = null;
    mock.onPost("/api/v1/saved-reports").reply((config) => {
      posted = JSON.parse(config.data as string);
      return [
        201,
        {
          id: "new-1",
          name: "May P&L",
          report_kind: "income_statement",
          filters: { date_from: "2026-05-01" },
          created_at: "2026-05-21T00:00:00Z",
          updated_at: "2026-05-21T00:00:00Z",
        },
      ];
    });

    render(
      <AppProviders>
        <SavedReportsControl
          reportKind="income_statement"
          currentFilters={{ date_from: "2026-05-01" }}
          onLoad={vi.fn()}
        />
      </AppProviders>,
    );

    const user = userEvent.setup();
    const name = await screen.findByTestId("saved-reports-name");
    await user.type(name, "May P&L");
    await user.click(screen.getByTestId("saved-reports-save"));
    await waitFor(() => expect(posted).not.toBeNull());

    const body = posted as Record<string, unknown>;
    expect(body.name).toBe("May P&L");
    expect(body.report_kind).toBe("income_statement");
    expect(body.filters).toEqual({ date_from: "2026-05-01" });
  });

  it("calls onLoad with the chosen preset's filters", async () => {
    mock.onGet("/api/v1/saved-reports").reply(200, [
      {
        id: "p-1",
        name: "Q1",
        report_kind: "income_statement",
        filters: { date_from: "2026-01-01", date_to: "2026-03-31" },
        created_at: "2026-05-21T00:00:00Z",
        updated_at: "2026-05-21T00:00:00Z",
      },
    ]);
    const onLoad = vi.fn();
    render(
      <AppProviders>
        <SavedReportsControl
          reportKind="income_statement"
          currentFilters={{}}
          onLoad={onLoad}
        />
      </AppProviders>,
    );

    const user = userEvent.setup();
    const select = (await screen.findByTestId(
      "saved-reports-select",
    )) as HTMLSelectElement;
    await user.selectOptions(select, "p-1");
    await waitFor(() => expect(onLoad).toHaveBeenCalled());
    expect(onLoad.mock.calls[0]![0]).toEqual({
      date_from: "2026-01-01",
      date_to: "2026-03-31",
    });
  });
});
