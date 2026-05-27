/**
 * Smoke test: the labels page renders without crashing and shows the
 * empty-state message when no products are picked.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ProductLabelsPage } from "@/pages/catalog/ProductLabels";

describe("<ProductLabelsPage />", () => {
  it("mounts and shows the empty-state message", () => {
    render(
      <MemoryRouter initialEntries={["/catalog/labels"]}>
        <Routes>
          <Route path="/catalog/labels" element={<ProductLabelsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("Product labels")).toBeInTheDocument();
    expect(
      screen.getByText(/Pick at least one product to preview labels/i),
    ).toBeInTheDocument();
  });
});
