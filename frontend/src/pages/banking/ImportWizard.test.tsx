import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ImportWizardPage } from "@/pages/banking/ImportWizard";
import { useAuthStore } from "@/store/useAuthStore";

const ACCOUNT_ID = "11111111-1111-1111-1111-111111111111";
const MAPPING_ID = "22222222-2222-2222-2222-222222222222";
const RUN_ID = "33333333-3333-3333-3333-333333333333";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/banking/imports/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/banking/imports/new" element={<ImportWizardPage />} />
          <Route path="/banking/imports" element={<div>imports-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<ImportWizardPage />", () => {
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
    mock.onGet("/api/v1/bank-import-mappings").reply(200, {
      items: [
        {
          id: MAPPING_ID,
          account_id: ACCOUNT_ID,
          name: "Chase CSV",
          file_kind: "csv",
          amount_sign: "signed_amount",
          column_map: {},
          delimiter: ",",
          encoding: "utf-8",
          has_header: true,
          date_format: "%Y-%m-%d",
          notes: null,
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by_user_id: "u",
        },
      ],
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("posts a multipart form with account, mapping and file", async () => {
    const user = userEvent.setup();
    let postUrl: string | undefined;
    let postData: unknown;
    mock.onPost("/api/v1/bank-imports").reply((config) => {
      postUrl = config.url;
      postData = config.data;
      return [
        201,
        {
          id: RUN_ID,
          account_id: ACCOUNT_ID,
          mapping_id: MAPPING_ID,
          filename: "stmt.csv",
          row_count: 3,
          inserted_count: 3,
          duplicate_count: 0,
          error_count: 0,
          imported_at: "2026-05-01T00:00:00Z",
          imported_by_user_id: "u",
          notes: null,
        },
      ];
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("wizard-account")).toBeInTheDocument(),
    );
    await user.selectOptions(screen.getByTestId("wizard-account"), ACCOUNT_ID);

    await waitFor(() =>
      expect(
        screen.getByTestId("wizard-mapping").querySelector(
          `option[value="${MAPPING_ID}"]`,
        ),
      ).not.toBeNull(),
    );
    await user.selectOptions(screen.getByTestId("wizard-mapping"), MAPPING_ID);

    const file = new File(["Date,Description,Amount\n"], "stmt.csv", {
      type: "text/csv",
    });
    await user.upload(screen.getByTestId("wizard-file"), file);

    await user.click(screen.getByTestId("wizard-submit"));

    await waitFor(() => expect(postUrl).toBe("/api/v1/bank-imports"));
    expect(postData).toBeInstanceOf(FormData);
    const fd = postData as FormData;
    expect(fd.get("account_id")).toBe(ACCOUNT_ID);
    expect(fd.get("mapping_id")).toBe(MAPPING_ID);
    expect(fd.get("file")).toBeInstanceOf(File);

    await waitFor(() =>
      expect(screen.getByTestId("wizard-result")).toBeInTheDocument(),
    );
  });
});
