import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MockAdapter from "axios-mock-adapter";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { apiClient } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { PartCreatePage } from "@/pages/catalog/PartCreate";
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
    <MemoryRouter initialEntries={["/catalog/parts/new"]}>
      <AppProviders>
        <Routes>
          <Route path="/catalog/parts/new" element={<PartCreatePage />} />
          <Route path="/catalog/parts/:id" element={<div>part detail</div>} />
        </Routes>
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("<PartCreatePage />", () => {
  let mock: MockAdapter;

  const calcResult = {
    pieces_per_set: 1,
    sets_required: 1,
    material_cost: "1.00",
    supply_cost: "0.00",
    labor_cost: "0.50",
    machine_cost: "0.25",
    overhead_cost: "0.10",
    total_cost: "1.85",
    cost_per_piece: "1.85",
    suggested_unit_price: "2.40",
    per_plate: [],
  };

  beforeEach(() => {
    mock = new MockAdapter(apiClient);
    setOwner();
    mock.onGet("/api/v1/printers").reply(200, { items: [] });
    mock.onGet("/api/v1/materials").reply(200, { items: [] });
    mock.onPost("/api/v1/jobs/calculate").reply(200, calcResult);
  });

  afterEach(() => {
    mock.restore();
  });

  it("creates a part and posts the print recipe", async () => {
    let posted: Record<string, unknown> | null = null;
    mock.onPost("/api/v1/parts").reply((config) => {
      posted = JSON.parse(config.data as string);
      return [201, { id: "33333333-3333-3333-3333-333333333333" }];
    });

    renderPage();
    const user = userEvent.setup();

    await user.type(screen.getByRole("textbox", { name: /name/i }), "Bracket");
    await user.clear(screen.getByTestId("part-print-minutes"));
    await user.type(screen.getByTestId("part-print-minutes"), "90");
    await user.clear(screen.getByTestId("part-parts-per-run"));
    await user.type(screen.getByTestId("part-parts-per-run"), "4");

    await user.click(screen.getByRole("button", { name: /create part/i }));

    await waitFor(() => expect(screen.getByText("part detail")).toBeInTheDocument());
    expect(posted).toMatchObject({
      name: "Bracket",
      print_minutes: 90,
      parts_per_run: 4,
    });
  });

  it("imports a gcode sidecar, pre-fills the recipe, and attaches its thumbnail", async () => {
    mock.onPost("/api/v1/parts/discover").reply(200, {
      print_minutes: 135,
      filament_grams_by_material: { slot_0: "42.5", slot_1: "7.25" },
      parts_per_set: 3,
      source_format: "prusaslicer",
      source_filename: "bracket.gcode.json",
      thumbnail_b64: btoa("fake-png-bytes"),
    });

    renderPage();
    const user = userEvent.setup();

    const file = new File(['{"x":1}'], "bracket.gcode.json", { type: "application/json" });
    await user.upload(screen.getByTestId("part-discovery-input"), file);

    // Print time + parts/run pre-filled from the parsed artifact.
    await waitFor(() =>
      expect(screen.getByTestId("part-print-minutes")).toHaveValue(135),
    );
    expect(screen.getByTestId("part-parts-per-run")).toHaveValue(3);

    // Import banner + one filament row per parsed slot (grams filled,
    // material left for the operator to pick).
    expect(screen.getByTestId("part-discovery-imported")).toHaveTextContent("bracket.gcode.json");
    expect(screen.getByTestId("part-discovery-imported")).toHaveTextContent(
      /embedded thumbnail will be attached/i,
    );
    expect(screen.getByTestId("part-material-0")).toHaveTextContent("slot_0");
    expect(screen.getByTestId("part-material-1")).toHaveTextContent("slot_1");
  });

  it("looks a recipe up from a printer and pre-fills it", async () => {
    mock.reset();
    setOwner();
    mock.onPost("/api/v1/jobs/calculate").reply(200, calcResult);
    mock.onGet("/api/v1/materials").reply(200, { items: [] });
    mock.onGet("/api/v1/printers").reply(200, {
      items: [
        {
          id: "p1",
          name: "Voron",
          slug: "voron",
          printer_type: "other",
          status: "active",
          moonraker_url: "http://printer.invalid:7125",
          moonraker_api_key_set: false,
          is_archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mock.onGet("/api/v1/printers/p1/gcode-files").reply(200, {
      items: [{ path: "bracket.gcode", size: 123, modified: 1700000000 }],
    });
    mock.onGet(/thumbnail/).reply(404); // thumbnails are best-effort
    mock.onPost("/api/v1/parts/discover-from-printer").reply((config) => {
      expect(JSON.parse(config.data as string)).toMatchObject({
        printer_id: "p1",
        filename: "bracket.gcode",
      });
      return [
        200,
        {
          print_minutes: 60,
          filament_grams_by_material: { PLA: "20.5" },
          parts_per_set: 2,
          source_format: "prusaslicer",
          source_filename: "bracket.gcode",
        },
      ];
    });

    renderPage();
    const user = userEvent.setup();

    await user.click(screen.getByTestId("part-discovery-printer"));
    // Modal opens and lists the printer's gcode file.
    const pick = await screen.findByTestId("browser-pick-bracket.gcode");
    await user.click(pick);

    await waitFor(() => expect(screen.getByTestId("part-print-minutes")).toHaveValue(60));
    expect(screen.getByTestId("part-parts-per-run")).toHaveValue(2);
    expect(screen.getByTestId("part-discovery-imported")).toHaveTextContent("bracket.gcode");
    expect(screen.getByTestId("part-discovery-imported")).toHaveTextContent(
      /thumbnail will be attached/i,
    );

    // On create, the printer thumbnail is attached as the part image.
    let imageReq: Record<string, unknown> | null = null;
    mock.onPost("/api/v1/parts").reply(201, { id: "55555555-5555-5555-5555-555555555555" });
    mock.onPost("/api/v1/parts/55555555-5555-5555-5555-555555555555/image/from-printer").reply(
      (config) => {
        imageReq = JSON.parse(config.data as string);
        return [204];
      },
    );

    await user.type(screen.getByRole("textbox", { name: /name/i }), "Bracket");
    await user.click(screen.getByRole("button", { name: /create part/i }));

    await waitFor(() => expect(screen.getByText("part detail")).toBeInTheDocument());
    expect(imageReq).toMatchObject({ printer_id: "p1", filename: "bracket.gcode" });
  });

  it("shows a live cost from the recipe", async () => {
    let calcReq: Record<string, unknown> | null = null;
    mock.onPost("/api/v1/jobs/calculate").reply((config) => {
      calcReq = JSON.parse(config.data as string);
      return [200, calcResult];
    });

    renderPage();
    const user = userEvent.setup();
    await user.clear(screen.getByTestId("part-print-minutes"));
    await user.type(screen.getByTestId("part-print-minutes"), "60");

    await waitFor(() => expect(screen.getByTestId("cost-total")).toHaveTextContent("$1.85"));
    // Costed as one plate of `parts_per_run` pieces (per-part basis).
    const inputs = (calcReq as { inputs?: { plates?: Array<{ parts_per_set: number }> } })?.inputs;
    expect(inputs?.plates?.[0]?.parts_per_set).toBe(1);
  });
});
