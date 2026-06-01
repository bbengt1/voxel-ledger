import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PartCreatePage } from "@/pages/catalog/PartCreate";
import { useAuthStore } from "@/store/useAuthStore";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/catalog/parts/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/parts/new" element={<PartCreatePage />} />
          <Route path="/catalog/parts/:id" element={<div>part detail</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PartCreatePage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    mock = new MockAdapter(apiClient);
    setOwner();
    mock.onGet("/api/v1/printers").reply(200, { items: [] });
    mock.onGet("/api/v1/materials").reply(200, { items: [] });
  });

  afterEach(() => {
    mock.restore();
  });

  it("creates a part and posts the print recipe", async () => {
    let posted: Record<string, unknown> | null = null;
    mock.onPost("/api/v1/parts").reply((config) => {
      posted = JSON.parse(config.data as string);
      return [201, { id: "33333333-3333-3333-3333-333333333333" }];
    });

    renderPage();
    const user = userEvent.setup();

    await user.type(screen.getByRole("textbox", { name: /name/i }), "Bracket");
    await user.clear(screen.getByTestId("part-print-minutes"));
    await user.type(screen.getByTestId("part-print-minutes"), "90");
    await user.clear(screen.getByTestId("part-parts-per-run"));
    await user.type(screen.getByTestId("part-parts-per-run"), "4");

    await user.click(screen.getByRole("button", { name: /create part/i }));

    await waitFor(() => expect(screen.getByText("part detail")).toBeInTheDocument());
    expect(posted).toMatchObject({
      name: "Bracket",
      print_minutes: 90,
      parts_per_run: 4,
    });
  });
});
