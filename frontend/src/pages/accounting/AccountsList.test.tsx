import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AccountsListPage } from "@/pages/accounting/AccountsList";

describe("<AccountsListPage />", () => {
  it("renders the chart-of-accounts stub heading", () => {
    render(
      <MemoryRouter>
        <AccountsListPage />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: /chart of accounts/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("accounts-stub")).toBeInTheDocument();
  });

  it("mentions the follow-up issue", () => {
    render(
      <MemoryRouter>
        <AccountsListPage />
      </MemoryRouter>,
    );
    expect(screen.getByText(/#69/i)).toBeInTheDocument();
  });
});
