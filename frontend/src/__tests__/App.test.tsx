import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "@/App";
import { AppProviders } from "@/app/AppProviders";

describe("<App />", () => {
  it("renders the hello screen on /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppProviders>
          <App />
        </AppProviders>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("hello-screen")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /voxel ledger/i }),
    ).toBeInTheDocument();
  });
});
