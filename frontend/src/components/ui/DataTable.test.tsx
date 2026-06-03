import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";

interface Row {
  id: string;
  name: string;
  qty: number;
  secret: string;
}

const ROW: Row = { id: "1", name: "Widget", qty: 5, secret: "hush" };

const columns: DataTableColumn<Row>[] = [
  { key: "name", header: "Name", cell: (r) => r.name, isPrimary: true },
  { key: "qty", header: "Qty", cell: (r) => String(r.qty), align: "right" },
  { key: "secret", header: "Secret", cell: (r) => r.secret, hideOnMobile: true },
  {
    key: "actions",
    header: "",
    cell: () => <button type="button">Do</button>,
    cardFullWidth: true,
  },
];

function renderTable(props?: Partial<React.ComponentProps<typeof DataTable<Row>>>) {
  return render(
    <DataTable
      columns={columns}
      rows={[ROW]}
      getRowKey={(r) => r.id}
      {...props}
    />,
  );
}

describe("<DataTable />", () => {
  it("renders both the desktop table and a mobile card from one column def", () => {
    renderTable();
    // Primary value shows in the desktop cell + the mobile card title.
    expect(screen.getAllByText("Widget")).toHaveLength(2);
    // A normal column's header (th) + mobile label (dt).
    expect(screen.getAllByText("Qty")).toHaveLength(2);
    expect(screen.getAllByText("5")).toHaveLength(2);
    // Actions cell appears in the desktop row + the mobile full-width footer.
    expect(screen.getAllByRole("button", { name: "Do" })).toHaveLength(2);
  });

  it("omits hideOnMobile columns from the card (desktop only)", () => {
    renderTable();
    // "Secret" header is in the desktop <th> only; its value in the <td> only.
    expect(screen.getAllByText("Secret")).toHaveLength(1);
    expect(screen.getAllByText("hush")).toHaveLength(1);
  });

  it("shows an empty message when there are no rows", () => {
    renderTable({ rows: [], emptyMessage: "No widgets." });
    expect(screen.getAllByText("No widgets.").length).toBeGreaterThanOrEqual(1);
  });

  it("shows a loading state", () => {
    renderTable({ loading: true });
    expect(screen.getAllByText("Loading…").length).toBeGreaterThanOrEqual(1);
  });
});
