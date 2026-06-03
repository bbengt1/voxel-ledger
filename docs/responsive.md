# Responsive / mobile conventions

Tracking epic: **#320** (phone & tablet friendly + installable PWA).

The app is **mobile-first**: base utility classes target phones (`<640px`); layer
`sm:` / `md:` / `lg:` upward for wider screens. Never write desktop-first styles
that a phone has to override.

## Breakpoints (Tailwind defaults)

| prefix | min-width | typical device |
|--------|-----------|----------------|
| (base) | 0         | phone          |
| `sm:`  | 640px     | large phone / small tablet |
| `md:`  | 768px     | tablet         |
| `lg:`  | 1024px    | desktop — **the sidebar becomes static here** |
| `xl:`  | 1280px    | wide desktop   |

The shell sidebar is an off-canvas **drawer below `lg:`** and a static left
column at `lg:+`.

## Use the shared primitives — don't hand-roll

| Need | Use | Notes |
|------|-----|-------|
| A list/data table | `@/components/ui/DataTable` | Desktop: scroll-safe `<table>`. Phone: a card per row. One column def drives both. **Do not** write a raw `<table>` for list data. |
| A filter row | `@/components/ui/FilterBar` | `1 → sm:2 → lg:N` grid. |
| Page title + actions | `@/components/layout/PageHeader` | Title + actions stack on phones. |
| A modal | `@/components/ui/Dialog` | Already inset on phones; pass `sheet` for long forms (full-height bottom sheet). |
| Branch behavior on width | `@/hooks/useBreakpoint` (`useMinWidth`, `useIsMobile`) | Only when CSS variants can't express it (e.g. focus-trapping a drawer). Prefer CSS otherwise. |

### `DataTable` column definition

```ts
const columns: DataTableColumn<Row>[] = [
  { key: "name", header: "Name", cell: (r) => r.name, isPrimary: true },
  { key: "total", header: "Total", cell: (r) => fmt(r.total), align: "right" },
  { key: "id", header: "ID", cell: (r) => r.id, hideOnMobile: true },
  { key: "actions", header: "", cell: (r) => <RowMenu row={r} />, cardFullWidth: true },
];
```

- `isPrimary` → the card title on phones.
- `hideOnMobile` → dropped from the card (keep only for low-value/wide columns).
- `cardFullWidth` → rendered label-less at the bottom of the card (actions menus).

## Anti-patterns (avoid; will be flagged once the regression guard lands)

- Raw `<table>` for list data → use `DataTable`.
- `grid grid-cols-2|3|4` with **no** responsive prefix on a form/filter → collapse
  to `grid-cols-1 sm:grid-cols-…`.
- Fixed pixel widths (`w-[720px]`, `min-w-[60rem]`) on top-level containers.
- `max-w-lg` modals without an inset (handled by `Dialog` now).

## Testing

- Unit-test shell + primitives at a mobile viewport (mock `matchMedia`; see
  `useBreakpoint.test.tsx`). jsdom doesn't apply CSS media queries, so both the
  `DataTable` desktop and card markup render in tests — assert with
  `getAllByText`.
- Spot-check pages visually at **375 / 768 / 1280px** before shipping a phase.
- Every frontend change must pass clean `tsc -b --force` + ESLint.
