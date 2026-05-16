import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { EmailLogPage } from "@/pages/admin/EmailLog";
import { useAuthStore } from "@/store/useAuthStore";

const EMAIL_ID = "44444444-4444-4444-4444-444444444444";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/admin/email-log"]}>
      <AppProviders>
        <Routes>
          <Route path="/admin/email-log" element={<EmailLogPage />} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

function emailRow(state: string, kind = "invoice") {
  return {
    id: EMAIL_ID,
    to_address: "buyer@example.test",
    from_address: "billing@example.test",
    subject: "Invoice INV-2026-0001",
    kind,
    state,
    attempts: 1,
    last_error: null,
    next_retry_at: null,
    provider_message_id: null,
    sent_at: null,
    subject_id: null,
    subject_kind: null,
    body_html_storage_key: "k",
    attachments_json: null,
    created_at: "2026-05-15T00:00:00Z",
    updated_at: "2026-05-15T00:00:00Z",
  };
}

describe("<EmailLogPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("lists messages, applies state filter, and retries", async () => {
    const user = userEvent.setup();
    let lastParams: Record<string, string> | undefined;
    mock.onGet("/api/v1/email-messages").reply((config) => {
      lastParams = config.params as Record<string, string>;
      return [200, { items: [emailRow("failed")] }];
    });
    let retried = false;
    mock
      .onPost(`/api/v1/email-messages/${EMAIL_ID}/retry`)
      .reply(() => {
        retried = true;
        return [200, emailRow("queued")];
      });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId(`email-row-${EMAIL_ID}`)).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByTestId("filter-state"), "failed");
    await waitFor(() => {
      expect(lastParams?.["state"]).toBe("failed");
    });

    await user.click(screen.getByTestId(`email-retry-${EMAIL_ID}`));
    await waitFor(() => {
      expect(retried).toBe(true);
    });
  });
});
