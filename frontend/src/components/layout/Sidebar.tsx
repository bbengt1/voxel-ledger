import { NavLink } from "react-router-dom";

import { cn } from "@/lib/cn";

interface NavItem {
  label: string;
  href: string;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

// Placeholder hrefs — real routes land in their respective phases. Using
// hash anchors keeps router happy without claiming a top-level path yet.
const SECTIONS: NavSection[] = [
  {
    label: "Catalog",
    items: [
      { label: "Products", href: "#catalog/products" },
      { label: "Materials", href: "#catalog/materials" },
    ],
  },
  {
    label: "Production",
    items: [
      { label: "Jobs", href: "#production/jobs" },
      { label: "Print queue", href: "#production/queue" },
    ],
  },
  {
    label: "Sales",
    items: [
      { label: "Orders", href: "#sales/orders" },
      { label: "Customers", href: "#sales/customers" },
    ],
  },
  {
    label: "Accounting",
    items: [
      { label: "Invoices", href: "#accounting/invoices" },
      { label: "Payments", href: "#accounting/payments" },
    ],
  },
  {
    label: "Reports",
    items: [{ label: "Overview", href: "#reports/overview" }],
  },
  {
    label: "Admin",
    items: [
      { label: "Users", href: "#admin/users" },
      { label: "Settings", href: "#admin/settings" },
    ],
  },
];

export function Sidebar() {
  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-56 flex-col gap-4 border-r border-border bg-muted/30 p-4"
    >
      <div className="text-base font-semibold tracking-tight">
        Voxel Ledger
      </div>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto">
        {SECTIONS.map((section) => (
          <div key={section.label} className="flex flex-col gap-1">
            <div className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {section.label}
            </div>
            <ul className="flex flex-col gap-0.5">
              {section.items.map((item) => (
                <li key={item.href}>
                  <NavLink
                    to={item.href}
                    className={({ isActive }) =>
                      cn(
                        "block rounded-md px-2 py-1.5 text-sm text-foreground/80 transition-colors",
                        "hover:bg-accent hover:text-accent-foreground",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        isActive && "bg-accent text-accent-foreground",
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}
