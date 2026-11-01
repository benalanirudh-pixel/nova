import { GUARDRAIL_TEXT } from "../lib/theme";

export default function GuardrailsBar({ text }: { text?: string }) {
  return (
    <div className="fixed bottom-0 inset-x-0 z-50 border-t border-negative/50 bg-negative/15 px-4 py-1.5 text-center text-xs text-negative">
      {text || GUARDRAIL_TEXT}
    </div>
  );
}
