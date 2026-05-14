import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { LocationDetailPage } from "@/pages/inventory/LocationDetail";
import { useAuthStore } from "@/store/useAuthStore";

const LID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function aLocation(overrides: Record<string, unknown> = {}) {
  return {
    id: LID,
    name: "Workshop bench",
    code: "WSB",
    kind: "workshop",
    description: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/inventory/locations/${LID}`]}>
      <AppProviders>
        <Routes>
          <Route
            path="/inventory/locations/:id"
            element={<LocationDetailPage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<LocationDetailPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders location details", async () => {
    setOwner();
    mock.onGet(`/api/v1/inventory/locations/${LID}`).reply(200, aLocation());
    renderPage();
    expect(await screen.findByText("Workshop bench")).toBeInTheDocument();
    expect(screen.getByTestId("location-code")).toHaveTextContent("WSB");
  });

  it("saves edits via PATCH", async () => {
    setOwner();
    mock.onGet(`/api/v1/inventory/locations/${LID}`).reply(200, aLocation());
    let patchBody: Record<string, unknown> | null = null;
    mock.onPatch(`/api/v1/inventory/locations/${LID}`).reply((config) => {
      patchBody = JSON.parse(config.data as string);
      return [200, aLocation({ name: "Workshop bench (main)" })];
    });
    renderPage();
    const nameInput = (await screen.findAllByDisplayValue("Workshop bench"))[0];
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Workshop bench (main)");
    await userEvent.click(screen.getByTestId("save-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("save-msg")).toHaveTextContent("Saved.");
    });
    expect(patchBody).toMatchObject({ name: "Workshop bench (main)" });
  });

  it("archive flow confirms before posting", async () => {
    setOwner();
    mock.onGet(`/api/v1/inventory/locations/${LID}`).reply(200, aLocation());
    let archiveCalled = false;
    mock
      .onPost(`/api/v1/inventory/locations/${LID}/archive`)
      .reply(() => {
        archiveCalled = true;
        return [200, aLocation({ is_archived: true })];
      });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderPage();
    await userEvent.click(await screen.findByTestId("archive-btn"));
    await waitFor(() => {
      expect(archiveCalled).toBe(true);
    });
    expect(confirmSpy).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("archive flow is cancellable", async () => {
    setOwner();
    mock.onGet(`/api/v1/inventory/locations/${LID}`).reply(200, aLocation());
    let archiveCalled = false;
    mock.onPost(`/api/v1/inventory/locations/${LID}/archive`).reply(() => {
      archiveCalled = true;
      return [200, aLocation({ is_archived: true })];
    });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    renderPage();
    await userEvent.click(await screen.findByTestId("archive-btn"));
    expect(confirmSpy).toHaveBeenCalled();
    expect(archiveCalled).toBe(false);
    confirmSpy.mockRestore();
  });
});
