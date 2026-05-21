import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { WebhooksSettingsPage } from "@/pages/settings/Webhooks";
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
    <MemoryRouter initialEntries={["/settings/webhooks"]}>
      <AppProviders>
        <Routes>
          <Route
            path="/settings/webhooks"
            element={<WebhooksSettingsPage />}
          />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<WebhooksSettingsPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("shows the secret banner after creating a subscription", async () => {
    mock.onGet("/api/v1/webhooks/subscriptions").reply(200, []);
    mock.onPost("/api/v1/webhooks/subscriptions").reply(201, {
      id: "sub-1",
      name: "n",
      target_url: "https://example.test/x",
      event_types: ["*"],
      is_active: true,
      created_by_user_id: null,
      created_at: "2026-05-21T00:00:00Z",
      updated_at: "2026-05-21T00:00:00Z",
      secret: "the-secret",
    });

    renderPage();

    const user = userEvent.setup();
    await waitFor(() =>
      expect(screen.getByTestId("webhook-new-form")).toBeInTheDocument(),
    );
    await user.type(screen.getAllByPlaceholderText("Name")[0]!, "n");
    await user.type(
      screen.getAllByPlaceholderText(/https:/)[0]!,
      "https://example.test/x",
    );
    await user.click(screen.getByRole("button", { name: /Create subscription/i }));

    await waitFor(() =>
      expect(screen.getByTestId("webhook-secret-banner")).toBeInTheDocument(),
    );
    expect(screen.getByText("the-secret")).toBeInTheDocument();
  });

  it("replay button POSTs to /replay", async () => {
    mock.onGet("/api/v1/webhooks/subscriptions").reply(200, []);
    mock.onGet("/api/v1/webhooks/deliveries").reply(200, [
      {
        id: "d-1",
        subscription_id: "s-1",
        event_id: null,
        event_type: "test.Event",
        payload: {},
        attempt_count: 3,
        last_status: "failed",
        last_response_code: 500,
        last_error: null,
        next_attempt_at: "2026-05-21T00:00:00Z",
        created_at: "2026-05-21T00:00:00Z",
        updated_at: "2026-05-21T00:00:00Z",
      },
    ]);
    let replayed = false;
    mock.onPost("/api/v1/webhooks/deliveries/d-1/replay").reply(() => {
      replayed = true;
      return [
        200,
        {
          id: "d-1",
          subscription_id: "s-1",
          event_id: null,
          event_type: "test.Event",
          payload: {},
          attempt_count: 3,
          last_status: "pending",
          last_response_code: 500,
          last_error: null,
          next_attempt_at: "2026-05-21T00:01:00Z",
          created_at: "2026-05-21T00:00:00Z",
          updated_at: "2026-05-21T00:01:00Z",
        },
      ];
    });

    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("webhook-tab-deliveries"));
    const button = await screen.findByTestId("webhook-replay-d-1");
    await user.click(button);
    await waitFor(() => expect(replayed).toBe(true));
  });
});
