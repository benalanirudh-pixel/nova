export type Maybe<T> = T | "N/A" | null | undefined;

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Real numbers only; anything else shows "N/A" (never a default). */
export function fmt(v: unknown, digits = 2): string {
  return isNum(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits }) : "N/A";
}
