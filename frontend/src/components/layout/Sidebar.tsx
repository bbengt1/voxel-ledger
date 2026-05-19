import { NavLink } from "react-router-dom";

import { cn } from "@/lib/cn";
import { useAuthStore, type Role } from "@/store/useAuthStore";

interface NavItem {
  label: string;
  href: string;
  /** If set, only roles in this list see the item. */
  visibleTo?: readonly Role[];
}

interface NavSection {
  label: string;
  items: NavItem[];
  /** Section is hidden entirely if no item is visible to the user. */
  visibleTo?: readonly Role[];
}

const ADMIN_ROLES: readonly Role[] = ["owner", "bookkeeper"];
const OWNER_ONLY: readonly Role[] = ["owner"];
const INVENTORY_WRITE_ROLES: readonly Role[] = ["owner", "production"];

// Placeholder hrefs — real routes land in their respective phases. Using
// hash anchors keeps router happy without claiming a top-level path yet.
const SECTIONS: NavSection[] = [
  {
    label: "Catalog",
    items: [
      { label: "Products", href: "/catalog/products" },
      { label: "Materials", href: "/catalog/materials" },
      { label: "Supplies", href: "/catalog/supplies" },
      { label: "Rates", href: "/catalog/rates" },
    ],
  },
  {
    label: "Inventory",
    items: [
      { label: "Locations", href: "/inventory/locations" },
      { label: "Transactions", href: "/inventory/transactions" },
      { label: "Alerts", href: "/inventory/alerts" },
      {
        label: "Starting balances",
        href: "/inventory/starting-balances",
        visibleTo: INVENTORY_WRITE_ROLES,
      },
    ],
  },
  {
    label: "Production",
    items: [
      { label: "Jobs", href: "/production/jobs" },
      { label: "Production queue", href: "/production/queue" },
      { label: "Printers", href: "/production/printers" },
    ],
  },
  {
    label: "AR",
    items: [
      { label: "Customers", href: "/customers" },
      { label: "Quotes", href: "/quotes" },
      { label: "Invoices", href: "/invoices" },
      { label: "Payments", href: "/payments" },
      { label: "Recurring", href: "/recurring-invoices" },
      { label: "Late-fee policies", href: "/late-fee-policies" },
      { label: "AR aging", href: "/reports/ar-aging" },
    ],
  },
  {
    label: "Sales",
    items: [
      { label: "Sales", href: "/sales" },
      { label: "POS", href: "/sales/pos" },
      { label: "Channels", href: "/sales/channels" },
      { label: "Shipments", href: "/sales?has_shipments=true" },
      { label: "Refunds", href: "#sales/refunds" },
    ],
  },
  {
    label: "AP",
    items: [
      { label: "Vendors", href: "/vendors" },
      { label: "Bills", href: "/bills" },
      { label: "Bill payments", href: "/bill-payments" },
      { label: "Recurring bills", href: "/recurring-bills" },
      { label: "Expense categories", href: "/expense-categories" },
      { label: "Expense claims", href: "/expense-claims" },
    ],
  },
  {
    label: "Banking",
    items: [
      { label: "Imports", href: "/banking/imports" },
      { label: "Mappings", href: "/banking/mappings" },
      { label: "Transactions", href: "/banking/transactions" },
      { label: "Match rules", href: "/banking/match-rules" },
      { label: "Reconciliation", href: "/banking/reconciliation" },
      { label: "Transfer", href: "/banking/transfer" },
    ],
  },
  {
    label: "Accounting",
    items: [
      { label: "Chart of accounts", href: "/accounting/accounts" },
      { label: "Journal entries", href: "/accounting/entries" },
      { label: "Periods", href: "/accounting/periods" },
      { label: "Divisions", href: "/accounting/divisions" },
      { label: "Budgets", href: "/accounting/budgets" },
      // --- 9.10a additions ---
      { label: "Fixed assets", href: "/assets" },
      { label: "Depreciation", href: "/depreciation" },
      { label: "Withholding profiles", href: "/withholding-profiles" },
    ],
  },
  {
    // Workflow is platform-level — the same approval surface will also
    // host refunds (Phase 6) and period-close finalization (Phase 4.3).
    // Top-level placement keeps it independent of any one domain.
    label: "Workflow",
    items: [{ label: "Approvals", href: "/approvals" }],
  },
  {
    label: "Reports",
    items: [{ label: "Overview", href: "#reports/overview" }],
  },
  {
    label: "Admin",
    visibleTo: ADMIN_ROLES,
    items: [
      { label: "Users", href: "/admin/users", visibleTo: ADMIN_ROLES },
      {
        label: "Custom fields",
        href: "/admin/custom-fields",
        visibleTo: OWNER_ONLY,
      },
      { label: "Email log", href: "/admin/email-log", visibleTo: ADMIN_ROLES },
      { label: "Settings", href: "#admin/settings", visibleTo: ADMIN_ROLES },
    ],
  },
];

export function Sidebar() {
  const role = useAuthStore((s) => s.user?.role);

  const visibleSections = SECTIONS.filter((section) => {
    if (section.visibleTo && (!role || !section.visibleTo.includes(role))) {
      return false;
    }
    // Hide the section if no items are visible to the user.
    return section.items.some(
      (item) => !item.visibleTo || (role && item.visibleTo.includes(role)),
    );
  });

  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-56 flex-col gap-4 border-r border-border bg-muted/30 p-4"
    >
      <div className="text-base font-semibold tracking-tight">
        Voxel Ledger
      </div>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto">
        {visibleSections.map((section) => (
          <div key={section.label} className="flex flex-col gap-1">
            <div className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {section.label}
            </div>
            <ul className="flex flex-col gap-0.5">
              {section.items
                .filter(
                  (item) =>
                    !item.visibleTo || (role && item.visibleTo.includes(role)),
                )
                .map((item) => (
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
