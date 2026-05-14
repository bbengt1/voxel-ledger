import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { TransferStockModal } from "@/components/inventory/TransferStockModal";

const LOCS = [
  {
    id: "loc-a",
    name: "Workshop",
    code: "WSB",
    kind: "workshop",
    description: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "loc-b",
    name: "Storage",
    code: "STG",
    kind: "workshop",
    description: null,
    is_archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

function renderModal(onTransferred = vi.fn()) {
  render(
    <TransferStockModal
      open
      onClose={() => {}}
      onTransferred={onTransferred}
      fixedEntity={{ id: "mat-1", label: "PLA Black", kind: "material" }}
    />,
  );
  return { onTransferred };
}

describe("<TransferStockModal />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    mock = new MockAdapter(apiClient);
    mock
      .onGet("/api/v1/inventory/locations")
      .reply(200, { items: LOCS, next_cursor: null });
  });
  afterEach(() => {
    mock.restore();
  });

  it("renders", () => {
    renderModal();
    expect(screen.getByText("Transfer stock")).toBeInTheDocument();
  });

  it("blocks submit when from == to", async () => {
    renderModal();
    await waitFor(() =>
      expect(screen.getByTestId("transfer-from")).toBeInTheDocument(),
    );
    const user = userEvent.setup();
    await user.selectOptions(screen.getByTestId("transfer-from"), "loc-a");
    await user.selectOptions(screen.getByTestId("transfer-to"), "loc-a");
    expect(screen.getByTestId("transfer-same-location")).toBeInTheDocument();
    expect(screen.getByTestId("transfer-submit")).toBeDisabled();
  });

  it("submits to /transfer with the right body", async () => {
    let observed: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/inventory/transactions/transfer").reply((cfg) => {
      observed = JSON.parse(cfg.data as string);
      return [
        201,
        {
          transfer_pair_id: "pair-1",
          out_transaction: { id: "tx-out" },
          in_transaction: { id: "tx-in" },
        },
      ];
    });
    const { onTransferred } = renderModal();
    await waitFor(() =>
      expect(screen.getByTestId("transfer-from")).toBeInTheDocument(),
    );
    const user = userEvent.setup();
    await user.selectOptions(screen.getByTestId("transfer-from"), "loc-a");
    await user.selectOptions(screen.getByTestId("transfer-to"), "loc-b");
    await user.type(screen.getByTestId("transfer-quantity"), "5");
    await user.click(screen.getByTestId("transfer-submit"));
    await waitFor(() => expect(onTransferred).toHaveBeenCalled());
    expect(observed).toMatchObject({
      entity_kind: "material",
      entity_id: "mat-1",
      from_location_id: "loc-a",
      to_location_id: "loc-b",
      quantity: "5",
    });
  });

  it("renders backend detail inline on 400", async () => {
    mock
      .onPost("/api/v1/inventory/transactions/transfer")
      .reply(400, { detail: "insufficient stock at source" });
    renderModal();
    await waitFor(() =>
      expect(screen.getByTestId("transfer-from")).toBeInTheDocument(),
    );
    const user = userEvent.setup();
    await user.selectOptions(screen.getByTestId("transfer-from"), "loc-a");
    await user.selectOptions(screen.getByTestId("transfer-to"), "loc-b");
    await user.type(screen.getByTestId("transfer-quantity"), "5");
    await user.click(screen.getByTestId("transfer-submit"));
    expect(await screen.findByTestId("transfer-error")).toHaveTextContent(
      "insufficient stock",
    );
  });
});
