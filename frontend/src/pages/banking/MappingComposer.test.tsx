import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { MappingComposerPage } from "@/pages/banking/MappingComposer";
import { useAuthStore } from "@/store/useAuthStore";
import { parseCsvPreview } from "@/components/banking/CsvPreviewParser";

const ACCOUNT_ID = "11111111-1111-1111-1111-111111111111";
const MAPPING_ID = "22222222-2222-2222-2222-222222222222";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/banking/mappings/new"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/banking/mappings/new"
            element={<MappingComposerPage />}
          />
          <Route
            path="/banking/mappings"
            element={<div>mappings-list</div>}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<MappingComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounts").reply(200, {
      items: [
        {
          id: ACCOUNT_ID,
          code: "1010",
          name: "Checking",
          type: "asset",
          is_archived: false,
          parent_account_id: null,
          description: null,
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

  it("fills the form and posts the create body", async () => {
    const user = userEvent.setup();
    let postBody: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/bank-import-mappings").reply((config) => {
      postBody = JSON.parse(config.data as string);
      return [
        201,
        {
          id: MAPPING_ID,
          name: postBody?.["name"],
          account_id: ACCOUNT_ID,
          file_kind: postBody?.["file_kind"],
          amount_sign: postBody?.["amount_sign"],
          column_map: postBody?.["column_map"],
          delimiter: postBody?.["delimiter"],
          encoding: postBody?.["encoding"],
          has_header: postBody?.["has_header"],
          date_format: postBody?.["date_format"],
          notes: null,
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ];
    });

    renderPage();

    await user.type(screen.getByTestId("mapping-name"), "Chase CSV");
    await waitFor(() =>
      expect(screen.getByTestId("mapping-account")).toBeInTheDocument(),
    );
    await user.selectOptions(screen.getByTestId("mapping-account"), ACCOUNT_ID);

    await user.type(screen.getByTestId("col-date"), "Date");
    await user.type(screen.getByTestId("col-description"), "Description");
    await user.type(screen.getByTestId("col-amount"), "Amount");

    await user.click(screen.getByTestId("save-mapping"));

    await waitFor(() => expect(postBody).toBeDefined());
    expect(postBody?.["name"]).toBe("Chase CSV");
    expect(postBody?.["account_id"]).toBe(ACCOUNT_ID);
    expect(postBody?.["file_kind"]).toBe("csv");
    expect(postBody?.["amount_sign"]).toBe("signed_amount");
    const colMap = postBody?.["column_map"] as Record<string, string>;
    expect(colMap["date"]).toBe("Date");
    expect(colMap["description"]).toBe("Description");
    expect(colMap["amount"]).toBe("Amount");
  });

  it("parses a 3-row CSV preview correctly", () => {
    const text = [
      "Date,Description,Amount",
      "2026-05-01,Coffee,-4.50",
      "2026-05-02,Refund,12.00",
      "2026-05-03,Paycheck,2500.00",
    ].join("\n");
    const rows = parseCsvPreview(text, {
      column_map: {
        date: "Date",
        description: "Description",
        amount: "Amount",
      },
      delimiter: ",",
      has_header: true,
      date_format: "%Y-%m-%d",
      amount_sign: "signed_amount",
    });
    expect(rows).toHaveLength(3);
    expect(rows[0]?.date).toBe("2026-05-01");
    expect(rows[0]?.description).toBe("Coffee");
    expect(rows[0]?.amount).toBe("-4.50");
    expect(rows[2]?.amount).toBe("2500.00");
  });
});
