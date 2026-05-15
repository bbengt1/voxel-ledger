/**
 * Collapsible chart-of-accounts tree, rendered recursively.
 *
 * Pure / presentational — fetch + filter happens in the page; this just
 * draws nodes and reports clicks + expansion via callbacks.
 */
import type { components } from "@/api/types";
import { cn } from "@/lib/cn";

export type AccountTreeNode = components["schemas"]["AccountTreeNode"];

interface Props {
  nodes: AccountTreeNode[];
  selectedId: string | null;
  expanded: Set<string>;
  onToggle: (id: string) => void;
  onSelect: (id: string) => void;
}

interface NodeRowProps extends Props {
  node: AccountTreeNode;
  depth: number;
}

function NodeRow({
  node,
  depth,
  selectedId,
  expanded,
  onToggle,
  onSelect,
  nodes: _allRoots,
}: NodeRowProps) {
  const hasChildren = !!node.children && node.children.length > 0;
  const isExpanded = expanded.has(node.id);
  const isSelected = selectedId === node.id;
  return (
    <li>
      <div
        className={cn(
          "flex cursor-pointer items-center gap-1 rounded px-1 py-0.5 text-sm",
          "hover:bg-accent hover:text-accent-foreground",
          isSelected && "bg-accent text-accent-foreground",
          node.is_archived && "text-muted-foreground line-through",
        )}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
        data-testid={`account-node-${node.id}`}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggle(node.id);
            }}
            aria-label={isExpanded ? "Collapse" : "Expand"}
            data-testid={`account-toggle-${node.id}`}
            className="inline-flex h-4 w-4 items-center justify-center text-xs text-muted-foreground"
          >
            {isExpanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="inline-block h-4 w-4" aria-hidden="true" />
        )}
        <button
          type="button"
          onClick={() => onSelect(node.id)}
          className="flex-1 truncate text-left"
          data-testid={`account-select-${node.id}`}
        >
          <span className="font-mono text-xs">{node.code}</span>{" "}
          <span>{node.name}</span>
        </button>
      </div>
      {hasChildren && isExpanded ? (
        <ul>
          {node.children!.map((child) => (
            <NodeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              expanded={expanded}
              onToggle={onToggle}
              onSelect={onSelect}
              nodes={_allRoots}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function AccountTree(props: Props) {
  if (props.nodes.length === 0) {
    return (
      <p className="px-2 py-4 text-sm text-muted-foreground">
        No accounts match the current filter.
      </p>
    );
  }
  return (
    <ul data-testid="account-tree">
      {props.nodes.map((node) => (
        <NodeRow
          key={node.id}
          node={node}
          depth={0}
          selectedId={props.selectedId}
          expanded={props.expanded}
          onToggle={props.onToggle}
          onSelect={props.onSelect}
          nodes={props.nodes}
        />
      ))}
    </ul>
  );
}

/**
 * Filter a tree by type and archived flag. Keeps a parent if any descendant
 * matches; otherwise drops it.
 */
export function filterTree(
  nodes: AccountTreeNode[],
  typeFilter: string,
  includeArchived: boolean,
): AccountTreeNode[] {
  function visit(node: AccountTreeNode): AccountTreeNode | null {
    const children =
      (node.children ?? [])
        .map(visit)
        .filter((c): c is AccountTreeNode => c !== null);
    const typeMatch = !typeFilter || node.type === typeFilter;
    const archivedMatch = includeArchived || !node.is_archived;
    if ((typeMatch && archivedMatch) || children.length > 0) {
      return { ...node, children };
    }
    return null;
  }
  return nodes
    .map(visit)
    .filter((n): n is AccountTreeNode => n !== null);
}

/** Walk the tree and collect every node id. Used to expand-all. */
export function allIds(nodes: AccountTreeNode[]): Set<string> {
  const out = new Set<string>();
  function visit(n: AccountTreeNode) {
    out.add(n.id);
    (n.children ?? []).forEach(visit);
  }
  nodes.forEach(visit);
  return out;
}

/** Find a node by id anywhere in the tree. */
export function findNode(
  nodes: AccountTreeNode[],
  id: string,
): AccountTreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const child = findNode(n.children ?? [], id);
    if (child) return child;
  }
  return null;
}

/** Flatten the tree to a list, breadth-first style — handy for parent pickers. */
export function flatten(nodes: AccountTreeNode[]): AccountTreeNode[] {
  const out: AccountTreeNode[] = [];
  function visit(n: AccountTreeNode) {
    out.push(n);
    (n.children ?? []).forEach(visit);
  }
  nodes.forEach(visit);
  return out;
}
