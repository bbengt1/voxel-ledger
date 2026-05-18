import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { ManualMatchModal } from "@/pages/banking/ManualMatchModal";
import { useAuthStore } from "@/store/useAuthStore";

const TX_ID = "11111111-1111-1111-1111-111111111111";
const JE_ID = "22222222-2222-2222-2222-222222222222";

describe("<ManualMatchModal />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().setSession({
      accessToken: "a",
      refreshToken: "r",
      user: { id: "u", email: "o@example.com", role: "owner" },
    });
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("posts the journal_entry_id to /match", async () => {
    const user = userEvent.setup();
    let body: Record<string, unknown> | undefined;
    mock.onPost(`/api/v1/bank-transactions/${TX_ID}/match`).reply((config) => {
      body = JSON.parse(config.data as string);
      return [200, {}];
    });

    let onDoneCalls = 0;
    render(
      <AppProviders>
        <ManualMatchModal
          txId={TX_ID}
          open={true}
          onOpenChange={() => {}}
          onDone={() => {
            onDoneCalls += 1;
          }}
        />
      </AppProviders>,
    );

    await user.type(screen.getByTestId("manual-match-je-id"), JE_ID);
    await user.click(screen.getByTestId("manual-match-submit"));

    await waitFor(() => expect(body).toBeDefined());
    expect(body?.["journal_entry_id"]).toBe(JE_ID);
    expect(onDoneCalls).toBe(1);
  });
});
