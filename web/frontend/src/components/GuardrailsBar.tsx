import { GUARDRAIL_TEXT } from "../lib/theme";

export default function GuardrailsBar({ text }: { text?: string }) {
  return (
    <div role="note" className="fixed inset-x-0 bottom-0 z-50 flex h-7 items-center justify-center gap-2 border-t border-negative/40 bg-[#1d1416] px-4 text-[12px] text-negative">
      <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
        <path d="M8 1.5l5.5 2v4c0 3.3-2.3 5.9-5.5 7-3.2-1.1-5.5-3.7-5.5-7v-4z" />
      </svg>
      <span className="truncate">{text || GUARDRAIL_TEXT}</span>
    </div>
  );
}
