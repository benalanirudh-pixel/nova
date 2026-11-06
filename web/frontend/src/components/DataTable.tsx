import { useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  flexRender, getCoreRowModel, getSortedRowModel, useReactTable,
  type ColumnDef, type Row, type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { cn } from "@/lib/utils";

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    align?: "left" | "right" | "center";
    /** extra classes for this column's cells (body only) */
    cell?: string;
    /** header tooltip / explanation */
    title?: string;
  }
}

const VIRTUAL_AFTER = 80; // below this, plain rows are cheaper than virtualization
const ROW_H = 28;

/**
 * Terminal table: click headers to sort (numbers sort high-first), sticky header,
 * virtualized rows for long lists. Missing values sort last either way.
 */
export default function DataTable<T>({
  data, columns, onRowClick, rowClass, rowStyle, initialSort = [], maxHeight, className = "", empty = "No rows.", label,
}: {
  data: T[];
  columns: ColumnDef<T, any>[]; // eslint-disable-line @typescript-eslint/no-explicit-any
  onRowClick?: (row: T) => void;
  rowClass?: (row: T) => string;
  rowStyle?: (row: T) => CSSProperties | undefined;
  initialSort?: SortingState;
  /** CSS max-height of the scroll area; required for virtualization to kick in */
  maxHeight?: string;
  className?: string;
  empty?: ReactNode;
  label?: string;
}) {
  const [sorting, setSorting] = useState<SortingState>(initialSort);
  const table = useReactTable({
    data, columns, state: { sorting }, onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(),
    sortDescFirst: true,
  });
  const rows = table.getRowModel().rows;
  const scroller = useRef<HTMLDivElement>(null);
  const virtual = !!maxHeight && rows.length > VIRTUAL_AFTER;
  const v = useVirtualizer({ count: virtual ? rows.length : 0, getScrollElement: () => scroller.current, estimateSize: () => ROW_H, overscan: 12 });
  const items = virtual ? v.getVirtualItems() : [];
  const padTop = items.length ? items[0].start : 0;
  const padBottom = items.length ? v.getTotalSize() - items[items.length - 1].end : 0;
  const shown: Row<T>[] = virtual ? items.map((i) => rows[i.index]) : rows;
  const align = (a?: string) => (a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left");
  const cols = table.getVisibleLeafColumns().length;

  return (
    <div ref={scroller} className={cn("overflow-auto", className)} style={maxHeight ? { maxHeight } : undefined}>
      <table className="w-full border-separate border-spacing-0 text-[12px]" aria-label={label}>
        <thead className="sticky top-0 z-10 bg-panel">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const meta = h.column.columnDef.meta;
                const sorted = h.column.getIsSorted();
                const sortable = h.column.getCanSort();
                return (
                  <th key={h.id} colSpan={h.colSpan} scope="col" title={meta?.title}
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : sortable ? "none" : undefined}
                    className={cn("whitespace-nowrap border-b border-line/30 px-2 py-1.5 text-[11px] font-normal text-muted", align(meta?.align))}>
                    {h.isPlaceholder ? null : sortable ? (
                      <button onClick={h.column.getToggleSortingHandler()}
                        className={cn("inline-flex items-center gap-1 rounded-sm hover:text-fg focus:outline-none focus-visible:ring-1 focus-visible:ring-accent", sorted && "text-accent", meta?.align === "right" && "flex-row-reverse")}>
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        <span className="w-2 text-[9px]" aria-hidden>{sorted === "asc" ? "▲" : sorted === "desc" ? "▼" : ""}</span>
                      </button>
                    ) : flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody className="font-mono tabular-nums">
          {rows.length === 0 && <tr><td colSpan={cols} className="px-2 py-3 font-sans text-muted">{empty}</td></tr>}
          {padTop > 0 && <tr aria-hidden><td colSpan={cols} style={{ height: padTop }} /></tr>}
          {shown.map((r) => (
            <tr key={r.id} onClick={onRowClick && (() => onRowClick(r.original))} style={rowStyle?.(r.original)}
              className={cn("group h-7 hover:bg-raised/70", onRowClick && "cursor-pointer", rowClass?.(r.original))}>
              {r.getVisibleCells().map((c) => (
                <td key={c.id} className={cn("border-t border-line/10 px-2", align(c.column.columnDef.meta?.align), c.column.columnDef.meta?.cell)}>
                  {flexRender(c.column.columnDef.cell, c.getContext())}
                </td>
              ))}
            </tr>
          ))}
          {padBottom > 0 && <tr aria-hidden><td colSpan={cols} style={{ height: padBottom }} /></tr>}
        </tbody>
      </table>
    </div>
  );
}
