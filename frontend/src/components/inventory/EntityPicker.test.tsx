import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import {
  EntityPicker,
  type EntityKind,
  type EntityOption,
} from "@/components/inventory/EntityPicker";

function Harness({ kind }: { kind: EntityKind }) {
  const [value, setValue] = useState<EntityOption | null>(null);
  return (
    <div>
      <EntityPicker
        kind={kind}
        value={value}
        onChange={setValue}
        data-testid="picker"
      />
      <div data-testid="selected">{value?.label ?? "(none)"}</div>
    </div>
  );
}

describe("<EntityPicker />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    mock = new MockAdapter(apiClient);
  });
  afterEach(() => {
    mock.restore();
  });

  it("queries the materials endpoint and lets the user pick an option", async () => {
    mock.onGet("/api/v1/materials").reply(200, {
      items: [
        { id: "m-1", name: "PLA Black" },
        { id: "m-2", name: "PETG Clear" },
      ],
      next_cursor: null,
    });

    render(<Harness kind="material" />);
    const user = userEvent.setup();
    const input = screen.getByTestId("picker-input");
    await user.click(input);
    expect(await screen.findByText("PLA Black")).toBeInTheDocument();
    await user.click(screen.getByText("PLA Black"));
    expect(screen.getByTestId("selected")).toHaveTextContent("PLA Black");
  });

  it("formats product options with their SKU", async () => {
    mock.onGet("/api/v1/products").reply(200, {
      items: [{ id: "p-1", name: "Widget", sku: "PROD-1" }],
      next_cursor: null,
    });
    render(<Harness kind="product" />);
    await userEvent.click(screen.getByTestId("picker-input"));
    await waitFor(() => {
      expect(screen.getByText(/Widget \(PROD-1\)/)).toBeInTheDocument();
    });
  });
});
