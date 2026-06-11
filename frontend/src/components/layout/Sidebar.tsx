import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

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
      { label: "Parts", href: "/catalog/parts" },
      { label: "Materials", href: "/catalog/materials" },
      { label: "Supplies", href: "/catalog/supplies" },
      { label: "Rates", href: "/catalog/rates" },
      { label: "Labels", href: "/catalog/labels" },
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
      { label: "Builds", href: "/production/builds" },
      { label: "Production queue", href: "/production/queue" },
      { label: "Cost calculator", href: "/production/cost-calculator" },
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
    ],
  },
  {
    label: "Sales",
    items: [
      { label: "Sales", href: "/sales" },
      { label: "POS", href: "/sales/pos" },
      { label: "Channels", href: "/sales/channels" },
      { label: "Shipments", href: "/sales?has_shipments=true" },
      { label: "Refunds", href: "/sales/refunds" },
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
      // --- 9.10a + 9.10b additions ---
      { label: "Fixed assets", href: "/assets" },
      { label: "Depreciation", href: "/depreciation" },
      { label: "Tax profiles", href: "/tax-profiles" },
      { label: "Tax remittances", href: "/tax-remittances" },
      { label: "Withholding profiles", href: "/withholding-profiles" },
      { label: "Settlements", href: "/settlements" },
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
    items: [
      // QBO replace-mode (#318 5d): financial statements + aging + tax
      // liability live in QuickBooks; only operational reports remain in-app.
      { label: "Financial reports (QuickBooks)", href: "/reports/quickbooks" },
      { label: "Sales by period", href: "/reports/sales-by-period" },
      { label: "Inventory valuation", href: "/reports/inventory-valuation" },
      { label: "Withholding 1099", href: "/reports/withholding-1099" },
    ],
  },
  {
    label: "Admin",
    visibleTo: ADMIN_ROLES,
    items: [
      { label: "Control Center", href: "/control-center", visibleTo: ADMIN_ROLES },
      { label: "Users", href: "/admin/users", visibleTo: ADMIN_ROLES },
      {
        label: "Custom fields",
        href: "/admin/custom-fields",
        visibleTo: OWNER_ONLY,
      },
      { label: "Email log", href: "/admin/email-log", visibleTo: ADMIN_ROLES },
      { label: "Webhooks", href: "/settings/webhooks", visibleTo: ADMIN_ROLES },
      { label: "QuickBooks", href: "/admin/quickbooks", visibleTo: OWNER_ONLY },
      { label: "Settings", href: "/admin/settings", visibleTo: ADMIN_ROLES },
    ],
  },
];

const EXPANDED_SECTION_KEY = "voxel-ledger.sidebar-expanded-section";

export function Sidebar() {
  const role = useAuthStore((s) => s.user?.role);
  const location = useLocation();

  const visibleSections = SECTIONS.filter((section) => {
    if (section.visibleTo && (!role || !section.visibleTo.includes(role))) {
      return false;
    }
    // Hide the section if no items are visible to the user.
    return section.items.some(
      (item) => !item.visibleTo || (role && item.visibleTo.includes(role)),
    );
  });

  // Initial expanded section: a persisted choice from this session,
  // otherwise the section containing the current route, otherwise the
  // first visible section. Updating ``location`` swaps to the new
  // route's section automatically.
  const sectionForPath = (pathname: string): string | null => {
    for (const section of visibleSections) {
      if (
        section.items.some(
          (item) =>
            item.href !== "#" &&
            pathname.startsWith(item.href.split("?")[0] ?? item.href),
        )
      ) {
        return section.label;
      }
    }
    return null;
  };

  const [expanded, setExpanded] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    const saved = window.sessionStorage.getItem(EXPANDED_SECTION_KEY);
    if (saved && visibleSections.some((s) => s.label === saved)) return saved;
    return sectionForPath(location.pathname) ?? visibleSections[0]?.label ?? null;
  });

  // Whenever the URL changes, open the section that owns the new
  // route. The operator can still collapse to ``null`` afterwards.
  useEffect(() => {
    const target = sectionForPath(location.pathname);
    if (target && target !== expanded) setExpanded(target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  // Persist the active choice so reopens in the same tab match.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (expanded) window.sessionStorage.setItem(EXPANDED_SECTION_KEY, expanded);
    else window.sessionStorage.removeItem(EXPANDED_SECTION_KEY);
  }, [expanded]);

  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-56 flex-col gap-4 border-r border-border bg-muted/30 p-4"
    >
      <Link
        to="/"
        className="rounded-md text-base font-semibold tracking-tight text-foreground hover:text-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Voxel Ledger home"
      >
        Voxel Ledger
      </Link>
      <div className="flex flex-1 flex-col gap-1 overflow-y-auto">
        {visibleSections.map((section) => {
          const isOpen = expanded === section.label;
          const visibleItems = section.items.filter(
            (item) =>
              !item.visibleTo || (role && item.visibleTo.includes(role)),
          );
          return (
            <div key={section.label} className="flex flex-col">
              <button
                type="button"
                onClick={() =>
                  setExpanded((prev) =>
                    prev === section.label ? null : section.label,
                  )
                }
                aria-expanded={isOpen}
                className={cn(
                  "flex items-center justify-between rounded-md px-2 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground",
                  "hover:bg-accent/40 hover:text-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
                data-testid={`sidebar-section-${section.label.toLowerCase().replace(/\s+/g, "-")}`}
              >
                <span>{section.label}</span>
                <span
                  aria-hidden="true"
                  className={cn(
                    "text-[10px] transition-transform",
                    isOpen ? "rotate-90" : "rotate-0",
                  )}
                >
                  ▶
                </span>
              </button>
              {isOpen ? (
                <ul className="mt-1 flex flex-col gap-0.5">
                  {visibleItems.map((item) => (
                    <li key={item.href}>
                      <NavLink
                        to={item.href}
                        // ``end`` so e.g. /sales doesn't highlight every
                        // /sales/* sibling at the same time. Every leaf
                        // in the sidebar should highlight only on an
                        // exact path match.
                        end
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
              ) : null}
            </div>
          );
        })}
      </div>
      <footer className="mt-2 border-t border-border pt-3 text-xs text-muted-foreground">
        <p className="font-medium">Bengtson Precision 3d</p>
        <p>All Rights Reserved {new Date().getFullYear()}</p>
      </footer>
    </nav>
  );
}
