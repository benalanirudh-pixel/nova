export type Maybe<T> = T | "N/A" | null | undefined;

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Real numbers only; anything else shows "N/A" (never a default). */
export function fmt(v: unknown, digits = 2): string {
  return isNum(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : "N/A";
}

/** Signed percent, e.g. "+1.23%". */
export const fmtPct = (v: unknown, digits = 2) => (isNum(v) ? `${v > 0 ? "+" : ""}${fmt(v, digits)}%` : "N/A");

/** Indian compact notation (L / Cr) for large counts like volume and OI. */
export const fmtCompact = (v: unknown) =>
  isNum(v) ? v.toLocaleString("en-IN", { notation: "compact", maximumFractionDigits: 2 }) : "N/A";

/** Tailwind text colour for the sign of a value; muted when missing. */
export const signCls = (v: unknown) =>
  !isNum(v) ? "text-muted" : v > 0 ? "text-positive" : v < 0 ? "text-negative" : "text-secondary";

/** API enum string -> readable label; "N/A" for missing. */
export const label = (s: unknown) => (typeof s === "string" && s && s !== "N/A" ? s.replaceAll("_", " ") : "N/A");
