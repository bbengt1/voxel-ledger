import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { CustomFieldsPage } from "@/pages/admin/CustomFields";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "owner@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/admin/custom-fields"]}>
      <AppProviders>
        <Routes>
          <Route path="/admin/custom-fields" element={<CustomFieldsPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<CustomFieldsPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders rows for the active entity tab", async () => {
    setOwner();
    mock
      .onGet(/\/api\/v1\/custom-fields\?entity_type=material.*/)
      .reply(200, {
        items: [
          {
            id: "11111111-1111-1111-1111-111111111111",
            entity_type: "material",
            key: "supplier_code",
            label: "Supplier Code",
            field_type: "string",
            required: false,
            display_order: 0,
            is_archived: false,
          },
        ],
      });

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Supplier Code")).toBeInTheDocument(),
    );
    expect(screen.getByText("supplier_code")).toBeInTheDocument();
  });

  it("shows select option editor when type=select", async () => {
    setOwner();
    mock
      .onGet(/\/api\/v1\/custom-fields\?entity_type=material.*/)
      .reply(200, { items: [] });

    renderPage();

    const typeSelect = await screen.findByRole("combobox");
    await userEvent.selectOptions(typeSelect, "select");

    expect(screen.getByLabelText("Select options")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /add option/i }),
    ).toBeInTheDocument();
  });

  it("POSTs a new field on submit", async () => {
    setOwner();
    mock
      .onGet(/\/api\/v1\/custom-fields\?entity_type=material.*/)
      .reply(200, { items: [] });

    const created = vi.fn(() => [
      201,
      {
        id: "22222222-2222-2222-2222-222222222222",
        entity_type: "material",
        key: "supplier_code",
        label: "Supplier Code",
        field_type: "string",
        required: false,
        display_order: 0,
        is_archived: false,
      },
    ]);
    mock.onPost("/api/v1/custom-fields").reply(() => created() as never);

    renderPage();

    const inputs = await screen.findAllByRole("textbox");
    await userEvent.type(inputs[0]!, "supplier_code");
    await userEvent.type(inputs[1]!, "Supplier Code");
    await userEvent.click(screen.getByRole("button", { name: /add field/i }));

    await waitFor(() => expect(created).toHaveBeenCalled());
  });
});

// vitest globals
import { vi } from "vitest";
