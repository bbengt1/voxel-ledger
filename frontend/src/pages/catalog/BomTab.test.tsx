import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { BomTab } from "@/pages/catalog/BomTab";
import { useAuthStore } from "@/store/useAuthStore";

const PID = "11111111-1111-1111-1111-111111111111";

function setOwner() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "o@example.com", role: "owner" },
  });
}

function setViewer() {
  useAuthStore.getState().setSession({
    accessToken: "a",
    refreshToken: "r",
    user: { id: "u", email: "v@example.com", role: "viewer" },
  });
}

function aBomItem(overrides: Record<string, unknown> = {}) {
  return {
    id: "22222222-2222-2222-2222-222222222222",
    parent_product_id: PID,
    component_kind: "material",
    component_id: "33333333-3333-3333-3333-333333333333",
    quantity: "100.000000",
    notes: null,
    resolved_name: "PLA-A",
    resolved_unit_cost: "20.000000",
    line_cost: "2000.000000",
    ...overrides,
  };
}

function renderTab() {
  return render(
    <AppProviders>
      <BomTab productId={PID} />
    </AppProviders>,
  );
}

describe("<BomTab />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    useAuthStore.getState().clearSession();
    localStorage.clear();
    mock = new MockAdapter(apiClient);
  });

  afterEach(() => {
    mock.restore();
  });

  it("renders the flat BOM with line costs", async () => {
    setOwner();
    mock
      .onGet(`/api/v1/products/${PID}/bom`)
      .reply(200, { items: [aBomItem()], total_cost: "2000.000000" });
    renderTab();
    expect(await screen.findByText("PLA-A")).toBeInTheDocument();
    expect(screen.getByTestId("bom-rollup").textContent).toContain("2000.000000");
  });

  it("renders the cost-unknown message when total_cost is null", async () => {
    setOwner();
    mock
      .onGet(`/api/v1/products/${PID}/bom`)
      .reply(200, { items: [], total_cost: null });
    renderTab();
    await waitFor(() =>
      expect(screen.getByTestId("bom-rollup").textContent).toMatch(/unknown/i),
    );
  });

  it("hides edit/delete controls for viewers", async () => {
    setViewer();
    mock
      .onGet(`/api/v1/products/${PID}/bom`)
      .reply(200, { items: [aBomItem()], total_cost: "2000.000000" });
    renderTab();
    expect(await screen.findByText("PLA-A")).toBeInTheDocument();
    expect(screen.queryByTestId("bom-add-btn")).not.toBeInTheDocument();
  });

  it("renders a cycle error inline above the add form", async () => {
    setOwner();
    mock
      .onGet(`/api/v1/products/${PID}/bom`)
      .reply(200, { items: [], total_cost: null });
    mock.onGet(/\/api\/v1\/materials/).reply(200, {
      items: [{ id: "m1", name: "PLA-A" }],
    });
    mock
      .onPost(`/api/v1/products/${PID}/bom`)
      .reply(400, { detail: "BOM cycle detected: would create cycle (...)" });
    renderTab();
    const user = userEvent.setup();
    await user.click(await screen.findByTestId("bom-add-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("bom-add-form")).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByTestId("bom-add-component")).toBeInTheDocument(),
    );
    const select = screen.getByTestId("bom-add-component") as HTMLSelectElement;
    await waitFor(() => expect(select.options.length).toBeGreaterThan(1));
    await user.selectOptions(select, "m1");
    await user.type(screen.getByTestId("bom-add-qty"), "100");
    await user.click(screen.getByTestId("bom-add-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("bom-add-error").textContent).toMatch(/cycle/i),
    );
  });

  it("edits a row's quantity inline", async () => {
    setOwner();
    let getCount = 0;
    mock.onGet(`/api/v1/products/${PID}/bom`).reply(() => {
      getCount += 1;
      if (getCount === 1) {
        return [200, { items: [aBomItem()], total_cost: "2000.000000" }];
      }
      return [
        200,
        {
          items: [aBomItem({ quantity: "250.000000", line_cost: "5000.000000" })],
          total_cost: "5000.000000",
        },
      ];
    });
    let patchedBody: Record<string, unknown> | undefined;
    mock
      .onPatch(
        `/api/v1/products/${PID}/bom/22222222-2222-2222-2222-222222222222`,
      )
      .reply((config) => {
        patchedBody = JSON.parse(config.data as string);
        return [200, aBomItem({ quantity: "250.000000" })];
      });
    renderTab();
    const user = userEvent.setup();
    await user.click(
      await screen.findByTestId("bom-edit-22222222-2222-2222-2222-222222222222"),
    );
    const input = screen.getByTestId(
      "bom-edit-input-22222222-2222-2222-2222-222222222222",
    ) as HTMLInputElement;
    await user.clear(input);
    await user.type(input, "250");
    await user.click(
      screen.getByTestId("bom-save-edit-22222222-2222-2222-2222-222222222222"),
    );
    await waitFor(() => expect(patchedBody?.["quantity"]).toBe("250"));
  });

  it("confirms before delete and refreshes on success", async () => {
    setOwner();
    let getCount = 0;
    mock.onGet(`/api/v1/products/${PID}/bom`).reply(() => {
      getCount += 1;
      if (getCount === 1) {
        return [200, { items: [aBomItem()], total_cost: "2000.000000" }];
      }
      return [200, { items: [], total_cost: null }];
    });
    let deleted = false;
    mock
      .onDelete(
        `/api/v1/products/${PID}/bom/22222222-2222-2222-2222-222222222222`,
      )
      .reply(() => {
        deleted = true;
        return [204];
      });
    renderTab();
    const user = userEvent.setup();
    await user.click(
      await screen.findByTestId("bom-delete-22222222-2222-2222-2222-222222222222"),
    );
    await user.click(
      screen.getByTestId("bom-confirm-delete-22222222-2222-2222-2222-222222222222"),
    );
    await waitFor(() => expect(deleted).toBe(true));
  });
});
