import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { TaxProfileComposerPage } from "@/pages/tax/TaxProfileComposer";
import { useAuthStore } from "@/store/useAuthStore";

const PROFILE_ID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/tax-profiles/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/tax-profiles/new" element={<TaxProfileComposerPage />} />
          <Route path="/tax-profiles/:id" element={<div>profile-detail</div>} />
          <Route path="/tax-profiles" element={<div>profiles-list</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<TaxProfileComposerPage />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/accounts").reply(200, {
      items: [
        { id: "acc-liab", code: "2210", name: "Tax Payable", type: "liability", is_archived: false },
      ],
    });
    setOwner();
  });

  afterEach(() => {
    mock.restore();
  });

  it("posts profile + each rate; compound toggle persists into the POST body", async () => {
    const user = userEvent.setup();
    let profileBody: Record<string, unknown> | undefined;
    const rateBodies: Array<Record<string, unknown>> = [];

    mock.onPost("/api/v1/tax-profiles").reply((config) => {
      profileBody = JSON.parse(config.data as string);
      return [201, { id: PROFILE_ID }];
    });
    mock.onPost(`/api/v1/tax-profiles/${PROFILE_ID}/rates`).reply((config) => {
      rateBodies.push(JSON.parse(config.data as string));
      return [201, { id: `rate-${rateBodies.length}` }];
    });

    renderPage();

    await user.type(screen.getByTestId("tp-code"), "US-CA-TEST");
    await user.type(screen.getByTestId("tp-name"), "CA Combined");

    // Add two rates; mark the second compound-on-previous.
    await user.click(screen.getByTestId("tp-add-rate"));
    await user.click(screen.getByTestId("tp-add-rate"));

    await user.type(screen.getByTestId("tp-rate-name-0"), "State");
    await user.selectOptions(screen.getByTestId("tp-rate-acct-0"), "acc-liab");

    await user.type(screen.getByTestId("tp-rate-name-1"), "County");
    await user.selectOptions(screen.getByTestId("tp-rate-acct-1"), "acc-liab");
    await user.click(screen.getByTestId("tp-rate-compound-1"));

    // Remove neither — leave both.
    await user.click(screen.getByTestId("tp-submit"));

    await waitFor(() => expect(profileBody).toBeDefined());
    expect(profileBody?.["code"]).toBe("US-CA-TEST");
    expect(profileBody?.["name"]).toBe("CA Combined");

    await waitFor(() => expect(rateBodies.length).toBe(2));
    expect(rateBodies[0]?.["name"]).toBe("State");
    expect(rateBodies[0]?.["compound_on_previous"]).toBe(false);
    expect(rateBodies[1]?.["name"]).toBe("County");
    expect(rateBodies[1]?.["compound_on_previous"]).toBe(true);
    expect(rateBodies[0]?.["ordinal"]).toBe(0);
    expect(rateBodies[1]?.["ordinal"]).toBe(1);
  });
});
