import type { ReactNode } from "react";
import { GUARDRAIL_TEXT } from "../lib/theme";

export default function GuardrailsBar({ text, children }: { text?: string; children?: ReactNode }) {
  return (
    <div role="note">
      <span>{text || GUARDRAIL_TEXT}</span>
      {children}
    </div>
  );
}
