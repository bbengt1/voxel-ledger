import { render, screen, waitFor } from "@testing-library/react";
import MockAdapter from "axios-mock-adapter";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PartOnHandSection } from "@/components/inventory/PartOnHandSection";

const PART_ID = "11111111-1111-1111-1111-111111111111";
const LOC_A = "22222222-2222-2222-2222-222222222222";
const LOC_B = "33333333-3333-3333-3333-333333333333";

describe("<PartOnHandSection />", () => {
  let mock: MockAdapter;

  beforeEach(() => {
    mock = new MockAdapter(apiClient);
    mock.onGet("/api/v1/inventory/locations").reply(200, {
      items: [
        { id: LOC_A, name: "Workshop A", code: "WS-A", kind: "workshop", is_archived: false },
        { id: LOC_B, name: "Workshop B", code: "WS-B", kind: "workshop", is_archived: false },
      ],
    });
  });

  afterEach(() => {
    mock.restore();
  });

  it("shows total + per-location on-hand for the part", async () => {
    mock.onGet("/api/v1/inventory/on-hand").reply((config) => {
      expect(config.params).toMatchObject({ entity_kind: "part", entity_id: PART_ID });
      return [
        200,
        {
          rows: [],
          summaries: [
            {
              entity_kind: "part",
              entity_id: PART_ID,
              total_on_hand: "7",
              per_location: { [LOC_A]: "5", [LOC_B]: "2" },
            },
          ],
        },
      ];
    });

    render(
      <AppProviders>
        <PartOnHandSection partId={PART_ID} />
      </AppProviders>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("part-on-hand-total")).toHaveTextContent("7");
    });
    const table = screen.getByTestId("part-on-hand-per-location");
    expect(table).toHaveTextContent("Workshop A");
    expect(table).toHaveTextContent("Workshop B");
  });

  it("renders a zero state when the part has no stock", async () => {
    mock.onGet("/api/v1/inventory/on-hand").reply(200, { rows: [], summaries: [] });

    render(
      <AppProviders>
        <PartOnHandSection partId={PART_ID} />
      </AppProviders>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("part-on-hand-total")).toHaveTextContent("0");
    });
    expect(screen.getByText("No stock on hand yet.")).toBeInTheDocument();
  });
});
