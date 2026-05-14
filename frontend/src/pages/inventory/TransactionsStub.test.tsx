import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TransactionsStubPage } from "./TransactionsStub";

describe("TransactionsStubPage", () => {
  it("renders the placeholder heading and Phase 3.4 hint", () => {
    render(<TransactionsStubPage />);
    expect(screen.getByText("Inventory transactions")).toBeInTheDocument();
    expect(screen.getByText(/Coming in Phase 3\.4/)).toBeInTheDocument();
  });
});
