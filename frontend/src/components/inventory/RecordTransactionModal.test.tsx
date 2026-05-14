import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { RecordTransactionModal } from "@/components/inventory/RecordTransactionModal";

const LOC = {
  id: "loc-1",
  name: "Workshop",
  code: "WSB",
  kind: "workshop",
  description: null,
  is_archived: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const MATERIAL = { id: "mat-1", name: "PLA Black", label: "PLA Black" };

function renderModal(
  overrides: { onRecorded?: ReturnType<typeof vi.fn> } = {},
) {
  const onRecorded = overrides.onRecorded ?? vi.fn();
  render(
    <RecordTransactionModal
      open
      onClose={() => {}}
      onRecorded={onRecorded}
      role="owner"
      fixedEntity={{ id: MATERIAL.id, label: MATERIAL.label, kind: "material" }}
      initialKind="receipt"
      initialLocationId="loc-1"
    />,
  );
  return { onRecorded };
}

describe("<RecordTransactionModal />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/inventory/locations").reply(200, {
      items: [LOC],
      next_cursor: null,
    });
  });
  afterEach(() => {
    mock.restore();
  });

  it("renders without crash", () => {
    renderModal();
    expect(screen.getByText("Record transaction")).toBeInTheDocument();
  });

  it("submits the form to the create endpoint with the right body", async () => {
    let observed: Record<string, unknown> | undefined;
    mock.onPost("/api/v1/inventory/transactions").reply((cfg) => {
      observed = JSON.parse(cfg.data as string);
      return [201, { id: "tx-1", quantity: "10", ...observed }];
    });
    const { onRecorded } = renderModal();
    await waitFor(() =>
      expect(screen.getByTestId("record-tx-location")).toHaveValue("loc-1"),
    );
    const user = userEvent.setup();
    await user.type(screen.getByTestId("record-tx-quantity"), "10");
    await user.click(screen.getByTestId("record-tx-submit"));
    await waitFor(() => expect(onRecorded).toHaveBeenCalled());
    expect(observed).toMatchObject({
      kind: "receipt",
      entity_kind: "material",
      entity_id: "mat-1",
      location_id: "loc-1",
      quantity: "10",
    });
  });

  it("renders the backend detail inline on 400", async () => {
    mock.onPost("/api/v1/inventory/transactions").reply(400, {
      detail: "negative inventory would result",
    });
    renderModal();
    await waitFor(() =>
      expect(screen.getByTestId("record-tx-location")).toHaveValue("loc-1"),
    );
    const user = userEvent.setup();
    await user.type(screen.getByTestId("record-tx-quantity"), "10");
    await user.click(screen.getByTestId("record-tx-submit"));
    expect(await screen.findByTestId("record-tx-error")).toHaveTextContent(
      "negative inventory",
    );
  });

  it("shows a spinner while in flight (Doherty)", async () => {
    mock.onPost("/api/v1/inventory/transactions").reply(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () => resolve([201, { id: "tx-1", quantity: "10" }]),
            200,
          ),
        ),
    );
    renderModal();
    await waitFor(() =>
      expect(screen.getByTestId("record-tx-location")).toHaveValue("loc-1"),
    );
    const user = userEvent.setup();
    await user.type(screen.getByTestId("record-tx-quantity"), "10");
    await user.click(screen.getByTestId("record-tx-submit"));
    expect(await screen.findByTestId("record-tx-spinner")).toBeInTheDocument();
  });

  it("filters kind options by role (sales sees only sale_out)", () => {
    render(
      <RecordTransactionModal
        open
        onClose={() => {}}
        onRecorded={vi.fn()}
        role="sales"
        fixedEntity={{
          id: MATERIAL.id,
          label: MATERIAL.label,
          kind: "material",
        }}
      />,
    );
    const select = screen.getByTestId("record-tx-kind") as HTMLSelectElement;
    const options = Array.from(select.querySelectorAll("option")).map(
      (o) => o.value,
    );
    expect(options).toEqual(["sale_out"]);
  });
});
