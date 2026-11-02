import type { NewsItem } from "../lib/types";

export function ago(iso?: string | null) {
  if (!iso) return "";
  const m = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60_000));
  return m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
}

/** Headlines open the source in a new tab; links are https-only (filtered by the API). */
export default function NewsList({ items }: { items: NewsItem[] }) {
  if (items.length === 0) return <div className="p-1 text-[12px] text-muted">No recent headlines found.</div>;
  return (
    <ul className="divide-y divide-line/15">
      {items.map((n) => (
        <li key={n.link}>
          <a href={n.link} target="_blank" rel="noopener noreferrer" className="group block px-1 py-2 focus:outline-none focus-visible:bg-raised">
            <div className="text-[13px] leading-snug text-fg group-hover:text-accent">{n.title}</div>
            <div className="mt-0.5 flex gap-2 text-[11px] text-muted">
              {n.source && <span className="text-secondary">{n.source}</span>}
              {n.published && <time dateTime={n.published} title={new Date(n.published).toLocaleString("en-IN")}>{ago(n.published)}</time>}
            </div>
          </a>
        </li>
      ))}
    </ul>
  );
}
